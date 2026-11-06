---
title: OpenSSH on musl のパスワード認証バイパス（*sshole）を、musl と OpenSSH のソースで確かめた。CVE はまだ振られていない
tags:
  - Security
  - OpenSSH
  - alpine
  - SRE
  - 脆弱性
private: true
updated_at: '2026-11-06T19:01:41+09:00'
id: a1790c68f85928fec09b
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

2026 年 11 月 5 日に、musl libc を使う Linux（Alpine など）の OpenSSH で、パスワードを持たないはずのアカウントにログインできてしまう問題が公開されました。通称「\*sshole」です。

この記事では、原因になっている musl の `crypt()` と OpenSSH のソルトの扱いを、どちらも公式リポジトリのソースで確かめました。確認したのは 2026 年 11 月 6 日です。状況は変わるので、使う前に出典のリンク先を見てください。

## 結論

- 鍵認証だけのつもりで `/etc/shadow` のパスワード欄を `*` にしているアカウントに、**257 バイト以上のパスワードを送るだけでログインできてしまう**ことがあります
- 原因は 2 つの仕様が噛み合ったことです。musl の `crypt()` は 256 バイトを超えるパスワードを処理できないとき `"*"` を返します。一方 OpenSSH は、パスワード欄が短くてソルトを取り出せないアカウントのために、別のアカウントからソルトを借ります。この結果、長いパスワードを送ると照合結果が `"*"` になり、保存されている `"*"` と一致してしまいます
- 成立する条件は厳しめです。musl である、PAM を使っていない、パスワード認証が有効、`*` のアカウントがある、`$5$`/`$6$` の実在ハッシュを持つアカウントが別にある、の全部が必要です
- 直し方は OpenSSH を 10.6p2（Alpine は後述のパッケージ版）に上げて sshd を再起動することです。すぐ上げられないなら `PasswordAuthentication no` で止められます
- **一次情報では、執筆時点で CVE 番号が割り当てられていません。**「CVE-2026-123158」と書いている記事もありますが、発見者のページと Alpine の勧告はどちらも未割り当てとしています。ここは番号を書かずに扱います

## 原因を 2 つに分けて見る

この問題は、musl 側と OpenSSH 側の 2 つの挙動が合わさって起きます。片方だけでは起きません。

### musl 側：長いパスワードだと `crypt()` が `"*"` を返す

musl の sha512crypt は、長すぎるパスワードによる計算量の増大を避けるため、鍵の長さに上限を設けています。[`src/crypt/crypt_sha512.c`][sha512] にそのまま書かれています。

```c
#define KEY_MAX 256
...
/* reject large keys */
for (i = 0; i <= KEY_MAX && key[i]; i++);
if (i > KEY_MAX)
    return 0;
```

256 バイトを超えると内部関数は `0`（ヌルポインタ）を返します。これを呼んでいるラッパー `__crypt_sha512` は、その `0` を見て `"*"` を返します。同じファイルの末尾です。

```c
char *__crypt_sha512(const char *key, const char *setting, char *output)
{
    ...
    p = sha512crypt(key, setting, output);
    /* self test and stack cleanup */
    q = sha512crypt(testkey, testsetting, testbuf);
    if (!p || q != testbuf || memcmp(testbuf, testhash, sizeof testhash))
        return "*";
    return p;
}
```

ファイル冒頭のコメントにも `on error "*" is returned.` と明記されています。この `"*"` を返す仕様自体は、プログラムが `crypt()` の戻り値を NULL チェックせずに使ってクラッシュするのを防ぐためのもので、musl としてはバグではありません。

この挙動は、Alpine（musl 1.2.5-r13）のコンテナで実際に動かして確かめました。`$6$` のソルトを与えて、パスワード長を 8・255・256・257 バイトで変えて `crypt()` を呼んだ結果です。

```c
const char *salt = "$6$abc0123456789$";
// 'A' を 8 / 255 / 256 / 257 バイト並べて crypt() に渡す
```

```text
len8   -> $6$abc0123456789$3JBC5N.mOrk0JFVcBUhVX0/9zYjFCJIeW/...
len255 -> $6$abc0123456789$0SSi/TsfMEXNq1anC2I8MV78hMZRfdMWXO...
len256 -> $6$abc0123456789$yj9Iwk1Z1KLVyIunzYUUGn0w/kISvr39zS...
len257 -> *
```

256 バイトまでは普通のハッシュが返り、257 バイトになった瞬間に `*` が返ります。勧告が言う「257 バイト以上で `*`」が、実際にそのとおりでした。

### OpenSSH 側：ソルトが取れないアカウントは、別のアカウントからソルトを借りる

OpenSSH は PAM を使わない構成のとき、保存されているハッシュをソルトの型として `crypt()` を呼び、結果を保存値と比べます。問題は、パスワード欄が `*` のアカウントだとソルトが取り出せないことです。

このとき OpenSSH は、他のアカウントを順に見て有効なソルトを探します。[`openbsd-compat/xcrypt.c`][xcrypt] の `pick_salt()` です。

```c
/*
 * Pick an appropriate password encryption type and salt for the running
 * system by searching through accounts until we find one that has a valid
 * salt.  Usually this will be root unless the root account is locked out.
 * ...
 */
static const char *
pick_salt(void)
{
    ...
    while ((pw = getpwent()) != NULL) {
        ...
        if (passwd[0] == '$' && (p = strrchr(passwd+1, '$')) != NULL) {
            ...
            strlcpy(salt, passwd, MINIMUM(typelen, sizeof(salt)));
            ...
        }
    }
    ...
}
```

これは CVE-2016-6210（ユーザー名の有無でレスポンス時間が変わってしまう問題）への対策として入った挙動です。存在しないユーザーや `*` のアカウントでも、実在アカウントのソルトを使って同じだけ計算することで、時間差からの推測を防ぐ目的でした。

### 2 つが噛み合うと

`*` のアカウント A にパスワード認証を試みると、こうなります。

1. A のパスワード欄 `*` からはソルトが取れないので、OpenSSH は別のアカウント B の `$6$ソルト$...` を借りる
2. 送られたパスワードを、その借りたソルトで `crypt()` にかける
3. パスワードが 257 バイト以上だと、musl の `crypt()` は `"*"` を返す
4. OpenSSH は照合結果 `"*"` を、A の保存値 `"*"` と比べる。一致するのでログインが通る

鍵専用にしていた root などのアカウントに、パスワードで入れてしまうことになります。

## 成立する条件

Alpine の勧告が挙げている条件は次のとおりです。どれか一つでも外れると成立しません。

| 条件 | 内容 |
| --- | --- |
| libc | musl であること（Alpine、OpenWrt など） |
| PAM | 使っていないこと（PAM なしビルド、または `UsePAM no`） |
| パスワード認証 | `PasswordAuthentication` が有効（既定値） |
| 標的アカウント | パスワード欄が `*` のアカウントが存在する |
| ソルト供給元 | `$5$` または `$6$` の実在ハッシュを持つアカウントが別に存在する |

glibc の多くのディストリビューション（Ubuntu、Debian、RHEL 系など）は musl ではないので、この経路では影響を受けません。Alpine でも、PAM 版（`openssh-server-pam`）を既定の `UsePAM yes` で使っていれば、パスワード照合が PAM 側になるため成立しません。

## 直し方と、すぐ上げられないときの止め方

一次情報が挙げている対応は 2 つです。

### 更新する

OpenSSH 本体では 10.6p2 で直っています。Alpine はブランチごとにパッケージ版が出ています（[Alpine の勧告][alpine]）。更新したら **sshd の再起動を忘れないでください**。

| Alpine ブランチ | 修正パッケージ |
| --- | --- |
| edge | 10.6_p2-r0 |
| 3.24 | 10.3_p1-r2 |
| 3.23 | 10.2_p1-r1 |
| 3.22 | 10.0_p1-r11 |
| 3.21 | 9.9_p2-r1 |

```console
# apk update && apk upgrade openssh-server
# rc-service sshd restart
```

### すぐ上げられないなら、パスワード認証を止める

`sshd_config` にこう書いて再起動します。

```
PasswordAuthentication no
```

```console
# rc-service sshd restart
```

鍵認証だけにしていた環境なら、そもそもパスワード認証はいらないはずなので、更新できるまでの間はこれで塞げます。自分の環境が該当するかどうかは、こう確認できます。

```console
# sshd を musl でビルドしているか（Alpine なら musl）
$ ldd $(which sshd) | head -1

# * のアカウントがあるか
$ awk -F: '$2=="*"{print $1}' /etc/shadow

# $5$ か $6$ のハッシュを持つアカウントがあるか
$ awk -F: '$2 ~ /^\$[56]\$/{print $1}' /etc/shadow

# パスワード認証が有効か（空なら既定の yes）
$ sshd -T 2>/dev/null | grep -i passwordauthentication
```

## 検証でわかったこと

- musl の `crypt()` が 257 バイト以上で `"*"` を返すことは、ソースで確認したうえで、Alpine（musl 1.2.5-r13）のコンテナで実際に `crypt()` を走らせて再現しました。256 バイトは普通のハッシュ、257 バイトは `*` という境界も実機で確認できました
- OpenSSH が他アカウントのソルトを借りる挙動も、公式リポジトリの `pick_salt()` のソースで確認しました。勧告の説明と食い違いはありませんでした
- この 2 つが噛み合うと `*` のアカウントにログインが通る、という組み立ては、上の 2 つの確認から導いたものです。実際に脆弱な sshd を立ててログインを突破する手順は、守る側に必要ないので載せていません
- 一方で、**CVE 番号は一次情報では未割り当て**でした。二次的な記事に載っている番号は、発見者のページにも Alpine の勧告にも出てきません。番号で検索しても一次情報にたどり着けないので、現時点では番号に頼らないほうが確実です

## 出典

- 発見者のページ: https://sshhole.com/
- Alpine Linux の勧告: https://alpinelinux.org/posts/2026-11-05-openssh-password-authentication-bypass/
- musl の sha512crypt のソース（256 バイト上限と `"*"` 返却）: https://git.musl-libc.org/cgit/musl/tree/src/crypt/crypt_sha512.c
- OpenSSH のソルト借用のソース（`pick_salt`）: https://github.com/openssh/openssh-portable/blob/master/openbsd-compat/xcrypt.c

[sha512]: https://git.musl-libc.org/cgit/musl/tree/src/crypt/crypt_sha512.c
[xcrypt]: https://github.com/openssh/openssh-portable/blob/master/openbsd-compat/xcrypt.c
[alpine]: https://alpinelinux.org/posts/2026-11-05-openssh-password-authentication-bypass/
