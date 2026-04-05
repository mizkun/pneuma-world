/**
 * ActionQueueManager — キャラクターごとのミニ行動キュー管理
 *
 * Phaser Scene から独立したロジック層。
 * Scene の update() から update(delta) を呼び出し、
 * アクション開始時のコールバック (onStartAction) を通じて
 * Scene 側に具体的な描画処理を委譲する。
 */

export interface MiniAction {
  action: string;       // "walk_to" | "interact" | "sit" | "idle_animation"
  target?: string;      // POI id
  animation?: string;   // アニメーション名
  duration: number;     // 秒数
}

export interface CharacterQueue {
  actions: MiniAction[];
  currentIndex: number;
  elapsedTime: number;   // 現在のアクションの経過時間（秒）
  isMoving: boolean;     // walk_to 移動中フラグ
  started: boolean;      // 現在のアクションが開始済みか
  paused: boolean;       // speech 中の一時停止
}

export type StartActionCallback = (charKey: string, action: MiniAction) => void;

export class ActionQueueManager {
  private queues: Map<string, CharacterQueue> = new Map();
  private onStartAction: StartActionCallback;

  constructor(onStartAction: StartActionCallback) {
    this.onStartAction = onStartAction;
  }

  /** キャラクターに新しい行動キューを設定 */
  setQueue(charKey: string, actions: MiniAction[]): void {
    this.queues.set(charKey, {
      actions,
      currentIndex: 0,
      elapsedTime: 0,
      isMoving: false,
      started: false,
      paused: false,
    });
  }

  /** キューを取得（テスト・デバッグ用） */
  getQueue(charKey: string): CharacterQueue | undefined {
    return this.queues.get(charKey);
  }

  /** キューが完了済み（全アクション消費 or 存在しない） */
  isQueueComplete(charKey: string): boolean {
    const queue = this.queues.get(charKey);
    if (!queue) return true;
    return queue.currentIndex >= queue.actions.length;
  }

  /** 一時停止 */
  pause(charKey: string): void {
    const queue = this.queues.get(charKey);
    if (queue) queue.paused = true;
  }

  /** 再開 */
  resume(charKey: string): void {
    const queue = this.queues.get(charKey);
    if (queue) queue.paused = false;
  }

  /** walk_to 移動完了通知 */
  notifyMoveComplete(charKey: string): void {
    const queue = this.queues.get(charKey);
    if (!queue) return;
    queue.isMoving = false;
    queue.currentIndex++;
    queue.elapsedTime = 0;
    queue.started = false;
  }

  /**
   * 毎フレーム呼び出し。delta はミリ秒。
   */
  update(delta: number): void {
    for (const [charKey, queue] of this.queues) {
      if (queue.paused) continue;
      if (queue.currentIndex >= queue.actions.length) continue;

      const currentAction = queue.actions[queue.currentIndex];

      // アクション未開始なら開始
      if (!queue.started) {
        queue.started = true;
        // walk_to は自動で isMoving にする
        if (currentAction.action === 'walk_to') {
          queue.isMoving = true;
        }
        this.onStartAction(charKey, currentAction);
      }

      // 移動中は時間経過で進めない（notifyMoveComplete で進む）
      if (queue.isMoving) continue;

      // duration チェック（秒）
      queue.elapsedTime += delta / 1000;
      if (queue.elapsedTime >= currentAction.duration) {
        queue.currentIndex++;
        queue.elapsedTime = 0;
        queue.started = false;
      }
    }
  }
}
