# 素材・ツールセットアップガイド（人間がやること）

Claude Code による実装と並行して、以下の準備をお願いします。

---

## 1. LimeZu Modern Interiors 購入

**URL**: https://limezu.itch.io/moderninteriors

- 16px 版が含まれていることを確認
- 購入後、ZIP をダウンロードして `viewer/public/tilesets/` に展開
- ライセンス: YouTube 配信での商用利用が可能か確認

### 確認ポイント
- [ ] タイルセット（床、壁、家具）が含まれている
- [ ] キャラクターの歩行スプライトシートが含まれている（4方向×3フレーム）
- [ ] 座りポーズが含まれているか確認（なければ下記で対応）

### キャラスプライトが含まれていない場合の代替案
- **LimeZu の別パック**: Modern Exteriors 等にキャラクターが含まれる場合がある
- **Universal LPC Spritesheet Generator**: https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/
  - ブラウザ上で髪型・服装を組み合わせてスプライトシート生成（無料）
  - 3人分のキャラを作成し、PNG でダウンロード

---

## 2. Tiled インストール

**URL**: https://www.mapeditor.org/

- Mac: `.dmg` をダウンロードしてインストール
- 部室マップの作成に使用

### マップ作成ガイドライン
- タイルサイズ: **16x16 px**（Phaser 側で zoom 2x して 32px 相当に表示）
- マップサイズ目安: **30x30 タイル**（480x480 px → zoom 2x で 960x960 px）
- 必要なレイヤー:
  1. **Floor**: 床タイル
  2. **Walls**: 壁タイル
  3. **Furniture**: 家具（机、椅子、棚、ソファ、PC、ホワイトボード）
  4. **Collision**: 歩けない領域（家具の上など）。easystar.js が使用
  5. **Objects** (Object Layer): POI の座標
     - `chair_1`, `chair_2`, `chair_3`: 椅子の座る位置
     - `bookshelf`: 棚の前
     - `pc`: PC の前
     - `whiteboard`: ホワイトボードの前
     - `sofa`: ソファの座る位置
     - `door`: 入口ドア
- エクスポート: **JSON** → `viewer/public/assets/clubroom.json`

---

## 3. キャラクター3人の名前・方向性

Issue #6 で以下のデフォルト案で実装済み:
- **葵（あおい）**: ムードメーカー。テンション高め、新しいもの好き
- **凛（りん）**: しっかり者。部長。コード書くのが得意
- **ひなた**: マイペース天然。絵を描くのが好き

変更したい場合は教えてください。

---

## チェックリスト

- [ ] LimeZu Modern Interiors 購入 + `viewer/public/tilesets/` に展開
- [ ] キャラスプライト確認（歩行アニメ、座りポーズ）
- [ ] Tiled インストール
- [ ] Tiled で部室マップ作成 + JSON エクスポート → `viewer/public/assets/clubroom.json`
