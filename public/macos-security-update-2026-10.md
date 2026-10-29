---
title: >-
  2026年10月26日の macOS セキュリティアップデート（27.2・26.7.2・15.8.2）を Apple の一次情報で読む。更新手順つき
tags:
  - macOS
  - Mac
  - セキュリティ
  - 脆弱性
  - SRE
private: false
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: false
---

## 先に結論

- 2026 年 10 月 26 日に、Apple は macOS Golden Gate 27.2、macOS Tahoe 26.7.2、macOS Sequoia 15.8.2 を公開しました。3 つを合わせて **299 件**の CVE が修正されています。
- Apple の公開情報には、今回の修正のうち**悪用が報告されたもの（いわゆるゼロデイ）はありません**。
- それでも、root 権限の取得、サンドボックスからの脱出、Gatekeeper の回避、リモートからのコード実行につながるものが多数含まれます。**早めに更新してください。**
- Tahoe と Sequoia では、Safari（WebKit）の修正は **Safari 27.2** として別に配信されています。macOS と Safari の両方を更新します。
- 9 月 28 日の更新（Tahoe 26.7.1、Sequoia 15.8.1）には、**悪用が報告された** CoreGraphics の脆弱性（CVE-2026-86950）の修正が入っていました。9 月から更新していない Mac は、こちらも未修正です。
- macOS Sonoma 向けの更新は、今回出ていません。Sonoma の最後のセキュリティ更新は 8 月 6 日の 14.8.9 です。

## どこを見たか

この記事の数字と記述は、すべて Apple の一次情報から取りました。

- [Apple security releases](https://support.apple.com/en-us/100100)（Apple のセキュリティ更新の一覧）
- [About the security content of macOS Golden Gate 27.2](https://support.apple.com/en-us/149521)
- [About the security content of macOS Tahoe 26.7.2](https://support.apple.com/en-us/149522)
- [About the security content of macOS Sequoia 15.8.2](https://support.apple.com/en-us/149523)
- [About the security content of Safari 27.2](https://support.apple.com/en-us/149527)
- [About the security content of macOS Tahoe 26.7.1](https://support.apple.com/en-us/149228) / [macOS Sequoia 15.8.1](https://support.apple.com/en-us/149229)
- [MacのmacOSをアップデートする](https://support.apple.com/ja-jp/108382)（更新手順）

CVE の件数は、各ページに載っている CVE 番号を重複なしで数えたものです（2026 年 10 月 29 日時点）。

## 今回の更新の全体像

| 更新 | 対象 | 公開日 | CVE の件数 |
|---|---|---|---|
| macOS Golden Gate 27.2 | macOS Golden Gate | 2026-10-26 | 263 |
| macOS Tahoe 26.7.2 | macOS Tahoe | 2026-10-26 | 213 |
| macOS Sequoia 15.8.2 | macOS Sequoia | 2026-10-26 | 197 |
| Safari 27.2 | macOS Sequoia、macOS Tahoe | 2026-10-26 | 33 |

3 つの macOS の更新は修正の多くが共通していて、重複を除くと 299 件です。

Golden Gate 27.2 のページには WebKit の修正も載っています。Tahoe と Sequoia のページには WebKit の項目がなく、その分は Safari 27.2 に入っています。

Apple のページで「Apple is aware of a report that this issue may have been exploited（悪用された可能性があるという報告を把握している）」と書かれた項目は、今回の 4 つのページにはありませんでした。

## 影響の大きい修正

Apple のページは、項目ごとに「コンポーネント」「Impact（影響）」「CVE」を載せています。Impact の文面から、影響が大きいものを種類別にまとめました。

### root 権限・カーネル権限の取得

アプリが root 権限を取れる、またはカーネル権限でコードを実行できる、という修正です。

| コンポーネント | Impact（Apple の記載） | CVE | 対象 |
|---|---|---|---|
| Kernel | An unprivileged attacker may be able to execute arbitrary code as root | CVE-2026-112438 | 3 つとも |
| Kernel | An app may be able to execute arbitrary code with kernel privileges | CVE-2026-86916 | Tahoe |
| Security | An app may be able to gain root privileges | CVE-2026-112668 ほか 2 件 | 3 つとも |
| CloudKit | A malicious app may be able to gain root privileges | CVE-2026-86896 | 3 つとも |
| configd、CVMS、Storage、StorageKit、SecurityAgent | An app may be able to gain root privileges | CVE-2026-112545 ほか | 3 つとも |
| CUPS | An app with App Sandbox restrictions may be able to escape the sandbox and execute code with root privileges | CVE-2026-84545 | Tahoe、Sequoia |

「アプリが」とあるものは、悪意のあるアプリを実行してしまったあとに、権限を広げられる種類の問題です。単独で外から侵入されるものではありませんが、ほかの脆弱性と組み合わされると被害が大きくなります。

### リモートから届くもの

ネットワーク越しに攻撃できる、と書かれている修正です。

| コンポーネント | Impact（Apple の記載） | CVE | 対象 |
|---|---|---|---|
| Remote Management | A remote attacker may be able to cause arbitrary code execution | CVE-2026-112427 | Golden Gate |
| Screen Sharing Server | A remote attacker may be able to cause unexpected app termination or heap corruption | CVE-2026-84590 | 3 つとも |
| Screen Sharing Server | A malicious Screen Sharing peer may be able to create arbitrary symlinks as root | CVE-2026-112511 | 3 つとも |
| smbx（SMB ファイル共有） | A remote attacker may be able to cause a denial-of-service or disclose process memory | CVE-2026-112451 | 3 つとも |
| afpfs | A remote attacker may be able to cause unexpected system termination or corrupt kernel memory | CVE-2026-64767 | Sequoia |
| App Store | A remote attacker may be able to break out of the WebContent sandbox | CVE-2026-112690 | 3 つとも |

画面共有、リモートマネジメント、ファイル共有を有効にしている Mac は、特に早く更新してください。使っていないなら、システム設定の「一般」→「共有」で切っておくと、これらの経路そのものが減ります。

### Web コンテンツ（WebKit）

細工された Web ページを開くと、任意のコードが実行されるおそれがある、という修正です。

| コンポーネント | Impact（Apple の記載） | 入っている更新 |
|---|---|---|
| WebKit、WebKit Canvas、WebKit JavaScript Bindings、WebKit Process Model | Processing maliciously crafted web content may lead to arbitrary code execution | Golden Gate 27.2、Safari 27.2 |
| WebKit Process Model | A remote attacker may be able to break out of Web Content sandbox | Golden Gate 27.2 |

Safari を使っていなくても、WebKit はアプリの中の Web 表示にも使われます。Tahoe と Sequoia では Safari 27.2 を入れないと、この修正は入りません。

### Gatekeeper・サンドボックス・プライバシー設定の回避

- **Gatekeeper の回避**: ArchiveService、BOM（ZIP の展開）、DesktopServices、LaunchServices、quarantine、System Settings など。ダウンロードしたファイルが、本来出るはずの確認なしに開ける問題です。
- **サンドボックスからの脱出**: AppleAVD、DiskArbitration、Kernel、libxpc、Printing、quarantine、Security、zsh など。
- **プライバシー設定（TCC）の回避**: Accounts、Control Center、Kernel、Photos Storage、Spotlight、Time Machine など。アプリが許可なくユーザーのデータにアクセスできる問題です。

## 9 月の更新を入れていない場合

9 月 28 日の macOS Tahoe 26.7.1 と macOS Sequoia 15.8.1 には、次の修正が入っていました。

| コンポーネント | Impact（Apple の記載） | CVE |
|---|---|---|
| CoreGraphics | Processing a maliciously crafted file may lead to arbitrary code execution. Apple is aware of a report that this issue may have been exploited in an extremely sophisticated attack against specific targeted individuals on versions of iOS before iOS 27. | CVE-2026-86950 |

こちらは**悪用が報告されています**。報告されている攻撃は特定の個人を狙った iOS への攻撃ですが、同じ問題が macOS にもありました。今回の 26.7.2 と 15.8.2 を入れれば、9 月の修正も含まれます。

## Sonoma 以前の Mac

Apple の一覧を見ると、10 月 26 日の更新は Golden Gate、Tahoe、Sequoia の 3 つだけで、macOS Sonoma 向けはありません。Safari 27.2 の対象も Sequoia と Tahoe です。

Sonoma の最後のセキュリティ更新は、2026 年 8 月 6 日の macOS Sonoma 14.8.9 です。Sonoma のままだと、9 月と 10 月に公開された修正は入りません。Sequoia 以降に上げられる Mac なら、上げてください。上げられない Mac は、ネットワークの共有機能を切る、知らないファイルを開かない、などで当面しのぐことになります。

## 更新の手順

### 1. 今のバージョンを確かめる

画面左上の Apple メニュー →「この Mac について」で、macOS のバージョンが表示されます。ターミナルなら次のコマンドです。

```sh
sw_vers -productVersion
```

| 使っている macOS | 今回の更新後のバージョン |
|---|---|
| Golden Gate | 27.2 |
| Tahoe | 26.7.2 |
| Sequoia | 15.8.2 |

Safari のバージョンは、Safari を開いてメニューの「Safari」→「Safari について」で確かめます。Tahoe と Sequoia では 27.2 になっていれば今回の修正が入っています。

### 2. システム設定から更新する

Apple の手順（[MacのmacOSをアップデートする](https://support.apple.com/ja-jp/108382)）のとおりです。Apple は、インストールの前に Mac のバックアップを作っておくことを勧めています。

1. Apple メニュー →「システム設定」を開く
2. サイドバーの「一般」→ 右側の「ソフトウェアアップデート」をクリックする
3. 「アップデート」「アップグレード」または「今すぐ再起動」のボタンをクリックする
4. 管理者のパスワード（Mac にログインするときのパスワード）を入力する
5. 終わるまで、スリープさせたりふたを閉じたりしない。途中で何度か再起動します

Tahoe と Sequoia で Safari 27.2 が別の項目として表示されたら、そちらも入れます。

「お使いのMacは最新の状態です」と出るのに更新が見えないときは、「アップデートを確認」をクリックするか、「command + R」キーを押すか、「ソフトウェアアップデート」をいったん閉じて開き直します。

### 3. ターミナルから更新する

複数台を手で回るときや、SSH で入っている Mac では、`softwareupdate` コマンドが使えます。

```sh
# 入れられる更新を一覧する
softwareupdate --list

# すべて入れて、必要なら再起動する
sudo softwareupdate --install --all --restart
```

`--list` で、macOS と Safari の更新が両方出ていることを確かめてから入れると確実です。再起動するまで修正は効かないので、作業中のファイルは先に保存してください。

### 4. 次から自動で入るようにする

ソフトウェアアップデートの画面にある自動アップデートの設定で、更新を自動でダウンロード・インストールするようにできます。Apple の一覧ページは、重要なバックグラウンドアップデートを許可する方法も案内しています。

会社の Mac を MDM で管理している場合は、端末側ではなく MDM の更新ポリシーで、今回のバージョンを必須にしておくのが確実です。

### 5. 更新できたか確かめる

もう一度 `sw_vers -productVersion` を実行して、上の表のバージョンになっていれば完了です。

## まとめ

- 10 月 26 日の macOS 更新は 3 バージョン合わせて 299 件の修正で、悪用の報告はありません。
- root 権限の取得、リモートからの攻撃、WebKit でのコード実行など影響の大きい修正が多く、更新を後回しにする理由はありません。
- Tahoe と Sequoia は Safari 27.2 も入れます。
- 9 月の更新を入れていない Mac には、悪用が報告された CVE-2026-86950 も残っています。
- Sonoma 向けは今回出ていないので、上げられる Mac は Sequoia 以降へ上げます。
