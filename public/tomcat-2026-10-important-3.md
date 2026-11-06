---
title: Tomcat 10月の Important 3件は既定の設定なら当たらない。使っているかの判定方法
tags:
  - Java
  - Tomcat
  - Security
  - SpringBoot
  - 脆弱性
private: true
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: false
---

2026 年 10 月 12 日に出た Apache Tomcat 11.0.27・10.1.61・9.0.123 で、深刻度 Important の脆弱性が 3 件直りました。レスポンスが別の人のものと混ざるもの 2 件と、パスワードなしで認証が通るもの 1 件です。

どれも、特定の機能を自分で有効にしている場合だけ当たります。この記事では、修正前の配布物（11.0.26・10.1.60・9.0.122）を公式アーカイブから落として、既定の `server.xml` で各機能が有効になっているかを確かめました。確認したのは 2026 年 11 月 7 日です。

## 結論

- **Tomcat を入れたままの設定なら、3 件とも当たりません。** 既定の `server.xml` では AJP と HTTP/2 はコメントアウトされていて、JNDIRealm の設定もありません
- 当たるのは、AJP コネクタを有効にしている（Apache httpd と AJP でつないでいる）、HTTP/2 を有効にして非同期サーブレットを使っている、LDAP 認証に JNDIRealm を GSSAPI 以外の SASL で使っている、のどれかの場合です
- どれにせよ、11.0.27・10.1.61・9.0.123 以上に上げれば直ります
- Spring Boot などの組み込み Tomcat も対象です。`tomcat-embed-core` のバージョンを確認してください

## 3 件の中身

| CVE | 内容 | 当たる条件 | 影響する版 |
| --- | --- | --- | --- |
| CVE-2026-103119 | AJP でレスポンスが次のリクエストに混ざる | AJP コネクタを使っている | 11.0.0-M25〜11.0.26（11 系のみ） |
| CVE-2026-101356 | HTTP/2 で利用者間のリクエスト・レスポンスが混ざる | HTTP/2 ＋ 非同期サーブレット | 11.0.22〜11.0.26、10.1.55〜10.1.60、9.0.118〜9.0.122 |
| CVE-2026-101296 | パスワードなしで認証が通る | JNDIRealm を GSSAPI 以外の SASL で使っている | 11.0.0-M1〜11.0.26、10.1.0-M1〜10.1.60、9.0.0.M1〜9.0.122 |

修正版はどれも 2026 年 10 月 12 日公開の **11.0.27・10.1.61・9.0.123** です（[Tomcat 11][sec11]・[10][sec10]・[9][sec9] のセキュリティページ）。

レスポンスが混ざる 2 件は、ある利用者向けの画面やデータが、別の利用者に返ってしまう可能性があるものです。ログイン後の画面を返すサービスだと、個人情報の漏れにつながります。

## 既定の設定では有効になっていない

修正前の 3 系列の配布物を[公式アーカイブ][archive]から落として、`conf/server.xml` を調べました。コメント（`<!-- -->`）の中は無効なので、コメントを除いて数えています。

| 版 | AJP コネクタ | HTTP/2 | JNDIRealm | 有効なコネクタ |
| --- | --- | --- | --- | --- |
| 11.0.26 | コメントアウト | コメントアウト | なし | 8080 / HTTP/1.1 |
| 10.1.60 | コメントアウト | コメントアウト | なし | 8080 / HTTP/1.1 |
| 9.0.122 | コメントアウト | コメントアウト | なし | 8080 / HTTP/1.1 |

どれも、有効なのは 8080 番の HTTP/1.1 だけでした。AJP も HTTP/2 も、設定例としてファイルに書かれていますがコメントの中です。

## 自分の環境を確かめる

### 1. バージョンを見る

```console
$ $CATALINA_HOME/bin/version.sh | grep "Server number"
```

11.0.27・10.1.61・9.0.123 以上なら対応済みです。

### 2. 3 つの機能を使っているか見る

```console
# AJP コネクタ（コメント外にあれば使っている）
$ grep -n 'AJP/1.3' $CATALINA_BASE/conf/server.xml

# HTTP/2
$ grep -n 'Http2Protocol' $CATALINA_BASE/conf/server.xml

# JNDIRealm（LDAP 認証）
$ grep -n 'JNDIRealm' $CATALINA_BASE/conf/server.xml $CATALINA_BASE/conf/context.xml
```

`grep` はコメントの中も拾うので、出てきた行が `<!-- -->` の中かどうかを目で確かめてください。JNDIRealm は、アプリの `META-INF/context.xml` に書かれていることもあります。

### 3. Spring Boot などの組み込み Tomcat の場合

組み込み Tomcat は `server.xml` を使いません。ライブラリのバージョンを見ます。

```console
# Maven
$ ./mvnw dependency:tree | grep tomcat-embed-core

# Gradle
$ ./gradlew dependencies --configuration runtimeClasspath | grep tomcat-embed-core
```

Spring Boot で HTTP/2 を有効にしているのは、`server.http2.enabled=true` を設定している場合です。Spring Boot の版をすぐ上げられないときは、Tomcat の版だけを上書きできます。

```xml
<!-- Maven（pom.xml） -->
<properties>
  <tomcat.version>10.1.61</tomcat.version>
</properties>
```

```groovy
// Gradle（build.gradle）
ext['tomcat.version'] = '10.1.61'
```

Spring Boot の版に合う Tomcat の系列（10.1 か 11 か）を選んでください。

## 直し方

- 11.0.27・10.1.61・9.0.123 以上に上げて、Tomcat を再起動します
- すぐ上げられないときは、使っていない機能を止めます。AJP は使っていなければコネクタを消す、HTTP/2 は `UpgradeProtocol` の行を消す、のが確実です
- JNDIRealm を SASL で使っている場合は、使っている仕組みが GSSAPI かどうかを確かめてください。GSSAPI 以外なら、上げるまでの間に別の認証方法へ切り替えることも考えます

## 出典

- Tomcat 11 のセキュリティ情報: https://tomcat.apache.org/security-11.html
- Tomcat 10 のセキュリティ情報: https://tomcat.apache.org/security-10.html
- Tomcat 9 のセキュリティ情報: https://tomcat.apache.org/security-9.html
- 配布物のアーカイブ: https://archive.apache.org/dist/tomcat/

[sec11]: https://tomcat.apache.org/security-11.html
[sec10]: https://tomcat.apache.org/security-10.html
[sec9]: https://tomcat.apache.org/security-9.html
[archive]: https://archive.apache.org/dist/tomcat/
