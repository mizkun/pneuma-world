import EasyStar from 'easystarjs';

export interface PathPoint {
  x: number;
  y: number;
}

/**
 * Convert flat collision data (from Tiled JSON) into a 2D grid.
 * 0 = walkable, 1 = blocked (any non-zero tile index).
 */
export function buildGridFromCollisionData(
  data: number[],
  width: number,
  height: number,
): number[][] {
  const grid: number[][] = [];
  for (let y = 0; y < height; y++) {
    const row: number[] = [];
    for (let x = 0; x < width; x++) {
      const tileIndex = data[y * width + x];
      row.push(tileIndex > 0 ? 1 : 0);
    }
    grid.push(row);
  }
  return grid;
}

/**
 * Find a path from (startX, startY) to (endX, endY) on the given grid.
 * Returns an array of PathPoints or null if no path exists.
 */
export function findPath(
  grid: number[][],
  startX: number,
  startY: number,
  endX: number,
  endY: number,
): Promise<PathPoint[] | null> {
  return new Promise((resolve) => {
    const easystar = new EasyStar.js();
    easystar.setGrid(grid);
    easystar.setAcceptableTiles([0]);

    easystar.findPath(startX, startY, endX, endY, (path: PathPoint[] | null) => {
      resolve(path);
    });

    easystar.calculate();
  });
}

/**
 * Create a reusable EasyStar instance configured with the given grid.
 */
export function createPathfinder(grid: number[][]): EasyStar.js {
  const easystar = new EasyStar.js();
  easystar.setGrid(grid);
  easystar.setAcceptableTiles([0]);
  return easystar;
}
