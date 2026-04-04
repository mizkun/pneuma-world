import Phaser from 'phaser';

/**
 * React <-> Phaser 中継層。
 * Phaser.Events.EventEmitter ベースのシングルトンで、
 * React 側と Phaser Scene 間のイベントを双方向に橋渡しする。
 */
class GameBridge extends Phaser.Events.EventEmitter {
  private static instance: GameBridge;

  static getInstance(): GameBridge {
    if (!GameBridge.instance) {
      GameBridge.instance = new GameBridge();
    }
    return GameBridge.instance;
  }

  /** React -> Phaser: WorldState 更新 */
  updateWorldState(data: any) {
    this.emit('world_state', data);
  }

  /** React -> Phaser: 発言の吹き出し表示 */
  showSpeech(data: { characterId: string; content: string }) {
    this.emit('speech', data);
  }

  /** React -> Phaser: ミニ行動キュー */
  updateActionQueue(data: any) {
    this.emit('action_queue', data);
  }
}

export const gameBridge = GameBridge.getInstance();
