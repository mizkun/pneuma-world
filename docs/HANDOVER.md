# pneuma-world 引き継ぎ資料

## プロジェクトの経緯

### Pneuma とは
Pneuma は「AIキャラクターに内面を与える」フレームワーク。性格（Big Five）、感情（PAD 3次元）、記憶（エピソード + セマンティック）、目標を持ったキャラクターが、会話を重ねるほど関係性を育てていく仕組み。

### 4本柱
1. **パーソナルアシスタント（ミラ）** — Discord bot として稼働中（pneuma-mira）
2. **ポッドキャスト AIアシスタント** — 新規開発（pneuma-podcast）
3. **キャラ同士の掛け合いエンタメ** — 目玉コンテンツ（pneuma-world が中核）
4. **コアの OSS 公開** — pneuma-core として公開済み

### リポジトリ分離の経緯（2026-03-14〜15）
元々 `pneuma` という単一リポジトリで開発していた。OSS 公開に向けてコアを切り出す計画を立て、以下の順序で分離を実施:

1. **#145**: Middleware Protocol 導入 + RuntimeEngine スリム化
2. **#146**: アプリ固有コード（vault, voice, task）をコアから分離
3. **#147**: Protocol を protocols/ パッケージに集約 + anthropic 依存排除
4. **#148**: monorepo 化（pneuma-core / pneuma-world / mira の3パッケージ）
5. **#149**: pneuma-core の PyPI 公開準備（README, LICENSE, examples）
6. **#150**: リポジトリ分離（各パッケージを独立リポジトリに）

元の `pneuma` リポジトリは archive 済み。

## リポジトリ構成

```
github.com/mizkun/
├── pneuma-core     (public)  — コアライブラリ（性格・感情・記憶・目標）
├── pneuma-world    (public)  — マルチキャラクター自律世界エンジン ← ここ
├── pneuma-mira     (private) — パーソナルアシスタント「ミラ」
└── pneuma-podcast  (private) — ポッドキャスト AIアシスタント
```

## pneuma-world の役割

複数の AI キャラクターが同じ空間で自律的に思考・行動・対話する「小さな世界」を作るエンジン。

### ユースケース: キャラ同士の掛け合いエンタメ
- 部室のような空間で 3〜5 人のキャラクターが自律行動
- ドラクエ風 2D Viewer でリアルタイム表示（将来）
- YouTube Live 24時間配信（将来）
- 学校の中で行動 → 放課後は Discord に集まって雑談

### 2層 tick システム
| 種類 | 間隔 | 処理 | LLM |
|------|------|------|-----|
| Visual tick | 毎秒〜数秒 | 移動・アニメーション | なし |
| Think tick | 10〜30分 | 状況認識 → 思考 → 行動決定 | あり |

### ThinkCycle（キャラクター自律思考ループ）
1. Perceive: 周囲の状況を認識
2. Think: LLM で内省（Thought のみ、Speech なし）
3. Decide: 行動を決定（何もしない / 移動 / 会話 / ツール使用）
4. Act: 行動を実行
5. Update: 状態更新

### コスト最適化
- Think の判断: Haiku（軽量）
- 会話・創作活動: Sonnet（品質重視）
- 月額目安: 3キャラ x 15分間隔で $45-65/月

## 現在の状態

### 実装済み
- WorldEngine（世界シミュレーション管理）
- WorldClock（2層 tick）
- ThinkCycle（自律思考ループ）
- InteractionBus（キャラ間メッセージ）
- ToolRegistry（外部ツール）
- WorldLog（テキストログ）
- ScenarioLoader（YAML シナリオ読み込み）
- サンプルシナリオ: ゆるキャン（3キャラ）

### テスト状況
- 169 パス / 23 失敗（シナリオファイルパス問題、軽微）
- パス問題: filter-repo でのリポジトリ分離時にパスがずれた。ScenarioLoader の相対パス解決を修正すれば解消する

### 未実装・今後の課題
- Viewer（ドラクエ風 2D Web UI）
- YouTube 配信パイプライン
- キャラクターの日記機能
- 小説風出力（1日のまとめを自動生成）
- Discord 連携（放課後モード）

## 技術的な要点

### pneuma-core との関係
pneuma-world は pneuma-core に依存する。キャラクターの内面処理（感情、記憶、応答生成）は全て pneuma-core の RuntimeEngine が担当。world はその上に「複数キャラの自律行動」というレイヤーを追加する。

```python
# world がキャラの応答を得るとき
from pneuma_core.runtime.engine import RuntimeEngine
from pneuma_core.models.message import MessageInput

# 既存の RuntimeEngine.process_message() をそのまま使う
response = await runtime_engine.process_message(
    MessageInput(content="...", sender_type="character", ...)
)
```

### import パス
- `pneuma_core.*` — コアライブラリ
- `pneuma_world.*` — このリポジトリ

### 設計原則
- 「キャラクターから見たら全部同じ」: 相手が人間でもキャラでもシステムでも、同じインターフェースで処理
- Protocol ベース: LLM, Storage は差し替え可能
- コスト意識: Think は Haiku、会話は Sonnet
