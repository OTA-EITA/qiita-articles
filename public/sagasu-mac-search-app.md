---
title: Evernote の代わりに、録音や写真の中身まで探せる Mac アプリを作った
tags:
  - Swift
  - macOS
  - SQLite
  - 個人開発
  - OCR
private: true
updated_at: '2026-11-14T13:14:43+09:00'
id: dc687054a515e377ddf7
organization_url_name: null
slide: false
ignorePublish: false
posting_campaign_uuid: null
agreed_posting_campaign_term: false
---

メモは Evernote、書類は PDF、写真は写真アプリ、打ち合わせの録音はボイスメモ。探すときに場所を思い出すところから始まるのが面倒で、全部まとめて中身で探せる Mac アプリを作りました。

https://github.com/OTA-EITA/sagasu

![検索の画面](https://raw.githubusercontent.com/OTA-EITA/sagasu/main/docs/search.png)

「倉庫」で探すと、ノートの本文と、ホワイトボードの写真に写っている文字の両方が出ます。処理はすべて Mac の中で行い、外には送りません。

この記事では、作りと、作っていて引っかかったところを書きます。

## 何で探せるか

| ファイル | 索引に入れるもの |
| --- | --- |
| ノート | アプリで書いた Markdown |
| テキスト・コード・CSV・メール | 本文 |
| Word・RTF・HTML・Excel・PowerPoint | 本文（Excel は文字のセル、PowerPoint はスライドの文字） |
| PDF | 本文。文字のないページ（スキャン）は OCR |
| 画像 | 写っている文字、写っているもの（人・料理・書類など）、撮影日 |
| 音声 | 話し声の文字起こし |
| 動画 | 10 秒ごとの画面の文字と写っているもの、話し声 |
| そのほか | ファイル名とフォルダ名 |

使っているのは macOS に入っているものだけです。

| 用途 | 使ったもの |
| --- | --- |
| 索引と検索 | SQLite FTS5（trigram） |
| 文字認識・画像の分類 | Vision |
| 文字起こし | Speech（端末内の認識だけ） |
| PDF | PDFKit |
| Word・RTF | `textutil` |
| 画面 | SwiftUI |

## 日本語は trigram で、分かち書きせずに探す

索引は SQLite の FTS5 で、トークナイザに trigram を使っています。文字列を 3 文字ずつ区切って索引にするので、日本語を単語に分けなくても部分一致で探せます。trigram は SQLite 3.34.0（2020 年 12 月）で入りました。

```sql
CREATE VIRTUAL TABLE chunks USING fts5(
  text, path UNINDEXED, kind UNINDEXED, loc UNINDEXED,
  tokenize='trigram'
);
```

`loc` には「p.3」「01:00」「画像の文字」のような、ファイルの中のどこかを入れています。結果に「何ページ目で当たったか」を出すためです。

注意が要るのは 2 文字以下の語です。公式の説明に、3 文字未満の部分文字列は全文検索では何にも当たらない、とあります。

> Substrings consisting of fewer than 3 unicode characters do not match any rows when used with a full-text query.
> https://www.sqlite.org/fts5.html

日本語は「帯広」「倉庫」のような 2 文字の語で探すことが多いので、これはそのままでは困ります。3 文字以上の語は `MATCH`、2 文字以下の語は `LIKE` で絞るように分けました。

```swift
let long = terms.filter { $0.count >= 3 }
let short = terms.filter { $0.count < 3 }
// long は  chunks MATCH '"語1" "語2"'
// short は text LIKE '%語%' ESCAPE '\'
```

同じページに、`ESCAPE` 付きの `LIKE` は索引を使えないとも書かれています。2 文字以下の語はどのみち索引を使えないので、ここは全件をなめる前提にしています。

## 取り出し方

### PDF は、文字がなければ画像にして OCR

PDFKit で各ページの文字を取り、20 文字に満たないページだけを画像にして Vision で読みます。スキャンした書類はこちらに回ります。

```swift
if text.trimmingCharacters(in: .whitespacesAndNewlines).count < 20 {
    let img = page.thumbnail(of: size, for: .mediaBox)
    text = ocr(img)  // VNRecognizeTextRequest、ja-JP と en-US
}
```

### 写真は、文字と「写っているもの」の両方

`VNRecognizeTextRequest` で文字を、`VNClassifyImageRequest` で写っているものを取ります。分類のラベルは `people` や `food` のような英語なので、よく使うものだけ日本語を足して、「人物」「料理」でも当たるようにしました。画面では英語を隠して日本語だけ見せています。

### PowerPoint の文字が、途中で切れて当たらなかった

pptx と xlsx は zip の中の XML から文字を取ります。最初はタグを空白に置き換えていたのですが、これだと当たらない語が出ました。

PowerPoint は、1 つの段落の文字を、書式ごとに細かく分けて持っています。

```xml
<a:p><a:r><a:t>山</a:t></a:r><a:r><a:t>田さん</a:t></a:r></a:p>
```

タグを空白にすると「山 田さん」になり、「山田さん」で探しても当たりません。段落の閉じタグだけ改行にして、ほかのタグは空文字で消すように直しました。

### 音声と動画

音声は `SFSpeechURLRecognitionRequest` で、`requiresOnDeviceRecognition = true` にして端末の中だけで文字にします。結果は 1 分ごとにまとめて、「12:00」のように位置を付けます。

動画は、10 秒ごとに `AVAssetImageGenerator` で画面を取り出して写真と同じように読み、音声は m4a に書き出してから文字起こしに回します。

## Xcode なしで .app を作る

Xcode は入れず、Command Line Tools の Swift だけで作っています。SwiftPM で実行ファイルを作り、`Info.plist` と一緒に `.app` の形に並べて、アドホック署名するだけです。

```sh
swift build -c release
mkdir -p Sagasu.app/Contents/MacOS
cp .build/release/Sagasu Sagasu.app/Contents/MacOS/
cp Resources/Info.plist Sagasu.app/Contents/
codesign --force --deep --sign - Sagasu.app
```

音声認識を使うので、`Info.plist` に `NSSpeechRecognitionUsageDescription` が要ります。

## 引っかかったところ

### 端末から直接起動すると、すぐ落ちる

ビルドした実行ファイルを端末から直接起動すると、音声認識の許可を求めた時点で、終了コード 134 で落ちました。`.app` を `open` で開くと落ちません。端末から起動すると、許可を求める主体が端末のアプリとして扱われ、その側に音声認識の説明文がないためだと考えています。

画面の確認用に端末から起動するときは、許可を求めないようにしました。

### 許可より先に取り込みが終わり、音声が「取り込み済み」になった

起動するとすぐ取り込みを始めていたので、許可の画面に答える前に音声ファイルが処理され、文字起こしなしで「取り込み済み」になっていました。次からは更新日時が同じなので、二度と読み直されません。

索引に「文字起こしをしたか」の列を足し、文字起こしができる状態なのに、その列が立っていない音声と動画は読み直すようにしました。取り込みも、許可の返事が来てから始めます。

### HOME を変えても、索引が本物の場所に書かれた

試験用に `HOME` を別のフォルダにして CLI を動かしたら、索引は本物の `~/Library/Application Support` に書かれていました。手元の索引に試験用のファイルが混ざったので、環境変数 `SAGASU_INDEX` で索引の場所を変えられるようにしました。

### 画面の確認

`screencapture` は画面収録の許可がない環境では「could not create image from display」で失敗します。そこで、起動時に環境変数 `SAGASU_SNAPSHOT` があれば、ウィンドウを `cacheDisplay(in:to:)` で PNG に書き出して終わるようにしました。README の画面もこれで撮っています。ただし Quick Look のプレビュー部分は、この方法では空になります。

## 試した結果

テキスト、Word、Excel、文字のある PDF、スキャンだけの PDF、写真、動画を 1 つずつ用意して取り込み、それぞれの中身の語で検索して当たることを確かめました。9 ファイルの取り込みは OCR と動画の画面読み取りを含めて 2.7 秒、検索はどれも 1 ミリ秒以内でした。ファイル数が少ないので、何万ファイルになったときの速さはまだ測っていません。

【公開前に記入：音声の文字起こしを実機で確かめた結果】

## おわりに

Evernote の代わりとして毎日使いながら、気になったところを直していきます。似たような「全部まとめて探したい」悩みがある方は、試してみてください。

https://github.com/OTA-EITA/sagasu
