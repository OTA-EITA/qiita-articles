# qiita-articles

[Qiita（@Nekorock）](https://qiita.com/Nekorock) の記事の原稿と画像です。[Qiita CLI](https://github.com/increments/qiita-cli) と GitHub Actions で投稿しています。

## 流れ

1. `public/<name>.md` に原稿を書き、画像は `images/<name>/` に置く（記事からは `raw.githubusercontent.com` の URL で参照）
2. `private: true`（限定共有）のまま main に push すると、[`publish`](.github/workflows/publish.yml) が Qiita に投稿する
3. 限定共有の URL で内容を確認する。コマンドや出力は実際に動かしたものだけを載せる
4. 確認できた記事を [`schedule.json`](schedule.json) に公開日時つきで追加する
5. [`scheduled`](.github/workflows/scheduled.yml) が月・水・金の 8:00（JST）に、日時を過ぎた記事を全体公開に切り替える

```json
{
  "npm-cooldown-lockfile.md": "2026-10-26T08:00:00+09:00"
}
```

## 守り

- Qiita CLI は公開から 7 日以上たった版を lockfile で固定し、`npm ci --ignore-scripts` で入れる（公式アクションは最新版を入れるため使っていない）
- アクションは SHA で固定し、[gha-guard](https://github.com/OTA-EITA/gha-guard) と [lockfile-guard](https://github.com/OTA-EITA/lockfile-guard) で検査
- Qiita のトークンは `read_qiita` / `write_qiita` のみで、リポジトリの Secrets（`QIITA_TOKEN`）に保存

## 記事のネタ帳

| # | テーマ | 状態 |
|---|---|---|
| 1 | npm のクールダウンは lockfile に入った版を止めない | 限定共有（確認待ち） |
| 2 | Alertmanager のラベルから Slack に `@channel` を埋め込まれる問題 | 未着手 |
| 3 | GitHub Actions の pwn request とスクリプト注入を自分のリポジトリで潰す | 未着手 |
| 4 | GitHub Actions → AWS の OIDC で `sub` 条件が甘いと何が起きるか | 未着手 |
| 5 | `terraform plan` の危険な変更を CI で止める | 未着手 |
| 6 | Trivy Operator の脆弱性レポートをトリアージする | 未着手 |
| 7 | EKS アップデート前に PDB とドレインを dry-run で確かめる | 未着手 |
| 8 | .env や API キーの漏洩を CI で止める | 未着手 |
| 9 | AWS WAF の誤遮断を調べる | 未着手 |
| 10 | MCP サーバーをつなぐ前の権限チェック | 未着手 |
