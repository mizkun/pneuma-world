import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  MiniAction,
  CharacterQueue,
  ActionQueueManager,
} from '../actionQueue/ActionQueueManager';

describe('ActionQueueManager', () => {
  let manager: ActionQueueManager;
  let onStartAction: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onStartAction = vi.fn();
    manager = new ActionQueueManager(onStartAction);
  });

  describe('setQueue', () => {
    it('should set a new action queue for a character', () => {
      const actions: MiniAction[] = [
        { action: 'walk_to', target: 'bookshelf', duration: 0 },
        { action: 'sit', target: 'chair_1', duration: 10 },
      ];
      manager.setQueue('aoi', actions);
      const queue = manager.getQueue('aoi');
      expect(queue).toBeDefined();
      expect(queue!.actions).toEqual(actions);
      expect(queue!.currentIndex).toBe(0);
      expect(queue!.elapsedTime).toBe(0);
      expect(queue!.isMoving).toBe(false);
    });

    it('should replace existing queue for the same character', () => {
      manager.setQueue('aoi', [{ action: 'idle_animation', duration: 5 }]);
      manager.setQueue('aoi', [{ action: 'sit', target: 'chair_1', duration: 3 }]);
      const queue = manager.getQueue('aoi');
      expect(queue!.actions.length).toBe(1);
      expect(queue!.actions[0].action).toBe('sit');
    });
  });

  describe('update', () => {
    it('should call onStartAction for the first action on first update', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);
      manager.update(100); // 100ms delta
      expect(onStartAction).toHaveBeenCalledWith('aoi', { action: 'sit', target: 'chair_1', duration: 5 });
    });

    it('should not call onStartAction again if action already started', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);
      manager.update(100);
      manager.update(100);
      // onStartAction called only once (started flag is set)
      expect(onStartAction).toHaveBeenCalledTimes(1);
    });

    it('should advance to next action when duration expires (non-moving)', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 2 },
        { action: 'idle_animation', animation: 'stretch', duration: 3 },
      ]);
      // First update starts the action
      manager.update(500);
      expect(onStartAction).toHaveBeenCalledTimes(1);

      // Accumulate 2 seconds total
      manager.update(1500); // 2s total elapsed
      // Still on first action at exactly 2s, should advance
      const queue = manager.getQueue('aoi');
      expect(queue!.currentIndex).toBe(1);

      // Next update should start second action
      manager.update(100);
      expect(onStartAction).toHaveBeenCalledTimes(2);
      expect(onStartAction).toHaveBeenLastCalledWith('aoi', { action: 'idle_animation', animation: 'stretch', duration: 3 });
    });

    it('should not advance walk_to action by elapsed time (isMoving = true)', () => {
      onStartAction.mockImplementation((_charKey: string, _action: MiniAction) => {
        // Simulate walk_to setting isMoving to true
      });
      manager.setQueue('aoi', [
        { action: 'walk_to', target: 'bookshelf', duration: 0 },
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);

      // walk_to starts -> manager sets isMoving
      manager.update(100);
      expect(onStartAction).toHaveBeenCalledTimes(1);

      // The queue should be marked as moving (walk_to auto-sets isMoving)
      const queue = manager.getQueue('aoi');
      expect(queue!.isMoving).toBe(true);

      // Many updates pass but walk_to doesn't advance by time
      manager.update(10000);
      expect(queue!.currentIndex).toBe(0); // still on walk_to
    });

    it('should advance from walk_to when notifyMoveComplete is called', () => {
      manager.setQueue('aoi', [
        { action: 'walk_to', target: 'bookshelf', duration: 0 },
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);
      manager.update(100); // start walk_to

      manager.notifyMoveComplete('aoi');
      const queue = manager.getQueue('aoi');
      expect(queue!.currentIndex).toBe(1);
      expect(queue!.isMoving).toBe(false);
    });

    it('should do nothing when queue is fully consumed', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 1 },
      ]);
      manager.update(500);  // start
      manager.update(600);  // 1.1s total -> advance past end
      const queue = manager.getQueue('aoi');
      expect(queue!.currentIndex).toBe(1); // past the end
      // No further calls
      onStartAction.mockClear();
      manager.update(1000);
      expect(onStartAction).not.toHaveBeenCalled();
    });

    it('should handle multiple characters independently', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 2 },
      ]);
      manager.setQueue('rin', [
        { action: 'idle_animation', animation: 'stretch', duration: 3 },
      ]);
      manager.update(100);
      expect(onStartAction).toHaveBeenCalledTimes(2);
    });
  });

  describe('pause / resume', () => {
    it('should not process queues while paused', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);
      manager.pause('aoi');
      manager.update(100);
      expect(onStartAction).not.toHaveBeenCalled();
    });

    it('should resume processing after resume is called', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 5 },
      ]);
      manager.pause('aoi');
      manager.update(100);
      expect(onStartAction).not.toHaveBeenCalled();

      manager.resume('aoi');
      manager.update(100);
      expect(onStartAction).toHaveBeenCalledTimes(1);
    });
  });

  describe('isQueueComplete', () => {
    it('should return true when all actions are consumed', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 0.5 },
      ]);
      manager.update(100);  // start
      manager.update(500);  // 0.6s -> exceeds duration
      expect(manager.isQueueComplete('aoi')).toBe(true);
    });

    it('should return true for unknown character', () => {
      expect(manager.isQueueComplete('unknown')).toBe(true);
    });

    it('should return false when actions remain', () => {
      manager.setQueue('aoi', [
        { action: 'sit', target: 'chair_1', duration: 10 },
      ]);
      manager.update(100);
      expect(manager.isQueueComplete('aoi')).toBe(false);
    });
  });
});
