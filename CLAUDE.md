# pneuma-world

複数キャラクターが自律的に思考・行動・対話する「小さな世界」エンジン。

## Language
日本語で対話する。

## Architecture
- engine.py — WorldEngine（世界シミュレーション管理）
- runner.py — CLI ランナー
- clock.py — WorldClock（2層 tick システム）
- think_cycle.py — ThinkCycle（キャラクター自律思考ループ）
- interaction_bus.py — キャラクター間メッセージ伝達
- tools.py — ToolRegistry（外部ツール管理）
- world_log.py — テキストログ出力
- models/ — WorldState, CharacterState, Action
- scenarios/ — シナリオ定義（YAML）

## Dependencies
- pneuma-core（コアライブラリ）

## Development
- TDD必須
- テスト実行: `.venv/bin/python -m pytest tests/ -x --tb=short`
