import { describe, it, expect } from 'vitest';
import { buildGridFromCollisionData, findPath } from '../pathfinding/Pathfinder';

describe('buildGridFromCollisionData', () => {
  it('should convert flat collision data array into 2D grid', () => {
    // 3x3 map: walls on edges, open in center
    const data = [1, 1, 1, 1, 0, 1, 1, 1, 1];
    const grid = buildGridFromCollisionData(data, 3, 3);
    expect(grid).toEqual([
      [1, 1, 1],
      [1, 0, 1],
      [1, 1, 1],
    ]);
  });

  it('should handle a fully open map', () => {
    const data = [0, 0, 0, 0, 0, 0, 0, 0, 0];
    const grid = buildGridFromCollisionData(data, 3, 3);
    expect(grid).toEqual([
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ]);
  });

  it('should handle rectangular maps', () => {
    const data = [1, 0, 0, 1, 0, 0];
    const grid = buildGridFromCollisionData(data, 3, 2);
    expect(grid).toEqual([
      [1, 0, 0],
      [1, 0, 0],
    ]);
  });
});

describe('findPath', () => {
  it('should find a path on an open grid', async () => {
    const grid = [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ];
    const path = await findPath(grid, 0, 0, 2, 2);
    expect(path).not.toBeNull();
    expect(path!.length).toBeGreaterThan(0);
    // Path should start at (0,0) and end at (2,2)
    expect(path![0]).toEqual({ x: 0, y: 0 });
    expect(path![path!.length - 1]).toEqual({ x: 2, y: 2 });
  });

  it('should return null when path is blocked', async () => {
    const grid = [
      [0, 1, 0],
      [0, 1, 0],
      [0, 1, 0],
    ];
    const path = await findPath(grid, 0, 0, 2, 0);
    expect(path).toBeNull();
  });

  it('should navigate around obstacles', async () => {
    const grid = [
      [0, 0, 0, 0, 0],
      [0, 1, 1, 1, 0],
      [0, 0, 0, 0, 0],
    ];
    const path = await findPath(grid, 0, 0, 4, 0);
    expect(path).not.toBeNull();
    expect(path!.length).toBeGreaterThan(0);
    expect(path![path!.length - 1]).toEqual({ x: 4, y: 0 });
    // Path should go around the obstacle (through row 0 or row 2)
    // Every point in the path should be on a walkable tile
    for (const p of path!) {
      expect(grid[p.y][p.x]).toBe(0);
    }
  });

  it('should return a single point when start equals end', async () => {
    const grid = [
      [0, 0],
      [0, 0],
    ];
    const path = await findPath(grid, 1, 1, 1, 1);
    // EasyStar returns empty or single-point path for same start/end
    expect(path).not.toBeNull();
  });
});
