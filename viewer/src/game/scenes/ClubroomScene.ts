import Phaser from 'phaser';
import { buildGridFromCollisionData, createPathfinder, type PathPoint } from '../pathfinding/Pathfinder';

/** Sprite‑sheet layout (16×32 frames, 56 cols per sheet row) */
const COLS_PER_ROW = 56;
const WALK_ROW = 1; // 32px‑row index for walk animations
const WALK_BASE = WALK_ROW * COLS_PER_ROW; // frame 56

/** Frame offsets inside walk row (6 frames each) */
const WALK_DOWN_START = WALK_BASE + 0;
const WALK_UP_START = WALK_BASE + 6;
const WALK_RIGHT_START = WALK_BASE + 12;
const WALK_LEFT_START = WALK_BASE + 18;

/** Idle frames (row 0): Down=0, Up=1, Right=2, Left=3 */
const IDLE_DOWN = 0;
// const IDLE_UP = 1;
// const IDLE_RIGHT = 2;
// const IDLE_LEFT = 3;

/** Character definitions */
interface CharacterDef {
  key: string;
  spriteFile: string;
  startTileX: number;
  startTileY: number;
}

const CHARACTERS: CharacterDef[] = [
  { key: 'aoi', spriteFile: 'Premade_Character_01.png', startTileX: 7, startTileY: 8 },
  { key: 'rin', spriteFile: 'Premade_Character_02.png', startTileX: 9, startTileY: 6 },
  { key: 'hinata', spriteFile: 'Premade_Character_03.png', startTileX: 11, startTileY: 8 },
];

const TILE_SIZE = 16;
const WALK_SPEED = 80; // pixels per second

export class ClubroomScene extends Phaser.Scene {
  private sprites: Map<string, Phaser.GameObjects.Sprite> = new Map();
  private collisionGrid: number[][] = [];
  private walkingChars: Set<string> = new Set();

  constructor() {
    super('ClubroomScene');
  }

  preload() {
    this.load.tilemapTiledJSON('clubroom', '/assets/clubroom.json');
    this.load.image(
      'room_builder',
      '/tilesets/moderninteriors-win/1_Interiors/16x16/Room_Builder_16x16.png',
    );
    this.load.image(
      'generic',
      '/tilesets/moderninteriors-win/1_Interiors/16x16/Theme_Sorter/1_Generic_16x16.png',
    );

    // Load character sprite sheets (16×32 per frame)
    const basePath =
      '/tilesets/moderninteriors-win/2_Characters/Character_Generator/0_Premade_Characters/16x16/';
    for (const char of CHARACTERS) {
      this.load.spritesheet(char.key, basePath + char.spriteFile, {
        frameWidth: 16,
        frameHeight: 32,
      });
    }
  }

  create() {
    const map = this.make.tilemap({ key: 'clubroom' });

    const roomBuilderTileset = map.addTilesetImage('room_builder', 'room_builder');
    const genericTileset = map.addTilesetImage('generic', 'generic');

    if (!roomBuilderTileset || !genericTileset) {
      console.error('Failed to load tilesets');
      return;
    }

    const tilesets = [roomBuilderTileset, genericTileset];

    map.createLayer('floor', tilesets);
    map.createLayer('walls', tilesets);
    const furnitureLayer = map.createLayer('furniture', tilesets);

    // collision layer is invisible — used for pathfinding
    const collisionLayer = map.createLayer('collision', tilesets);
    if (collisionLayer) {
      collisionLayer.setVisible(false);
    }

    // Build pathfinding grid from collision layer data
    const collisionLayerData = map.getLayer('collision');
    if (collisionLayerData) {
      const flatData: number[] = [];
      for (let y = 0; y < collisionLayerData.height; y++) {
        for (let x = 0; x < collisionLayerData.width; x++) {
          const tile = collisionLayerData.data[y][x];
          flatData.push(tile.index);
        }
      }
      this.collisionGrid = buildGridFromCollisionData(
        flatData,
        collisionLayerData.width,
        collisionLayerData.height,
      );
    }

    // Create character animations & sprites
    this.createCharacterAnimations();
    this.createCharacterSprites(furnitureLayer);

    // Set camera bounds to map size
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);

    // Debug: click to move aoi to clicked tile
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      const worldPoint = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
      const tileX = Math.floor(worldPoint.x / TILE_SIZE);
      const tileY = Math.floor(worldPoint.y / TILE_SIZE);
      this.moveCharacterTo('aoi', tileX, tileY);
    });
  }

  private createCharacterAnimations() {
    for (const char of CHARACTERS) {
      const k = char.key;

      // Walk animations (6 frames each direction)
      this.anims.create({
        key: `${k}-walk-down`,
        frames: this.anims.generateFrameNumbers(k, {
          start: WALK_DOWN_START,
          end: WALK_DOWN_START + 5,
        }),
        frameRate: 8,
        repeat: -1,
      });
      this.anims.create({
        key: `${k}-walk-up`,
        frames: this.anims.generateFrameNumbers(k, {
          start: WALK_UP_START,
          end: WALK_UP_START + 5,
        }),
        frameRate: 8,
        repeat: -1,
      });
      this.anims.create({
        key: `${k}-walk-right`,
        frames: this.anims.generateFrameNumbers(k, {
          start: WALK_RIGHT_START,
          end: WALK_RIGHT_START + 5,
        }),
        frameRate: 8,
        repeat: -1,
      });
      this.anims.create({
        key: `${k}-walk-left`,
        frames: this.anims.generateFrameNumbers(k, {
          start: WALK_LEFT_START,
          end: WALK_LEFT_START + 5,
        }),
        frameRate: 8,
        repeat: -1,
      });
    }
  }

  private createCharacterSprites(furnitureLayer: Phaser.Tilemaps.TilemapLayer | null) {
    const furnitureDepth = furnitureLayer ? furnitureLayer.depth : 0;

    for (const char of CHARACTERS) {
      // Place sprite at center of tile. Origin at bottom-center so feet align to tile.
      const x = char.startTileX * TILE_SIZE + TILE_SIZE / 2;
      const y = (char.startTileY + 1) * TILE_SIZE; // bottom of the tile

      const sprite = this.add.sprite(x, y, char.key, IDLE_DOWN);
      sprite.setOrigin(0.5, 1); // anchor at bottom-center
      sprite.setDepth(furnitureDepth + 1 + char.startTileY * 0.01); // sort by Y
      this.sprites.set(char.key, sprite);
    }
  }

  /**
   * Move a character to the target tile using pathfinding.
   */
  moveCharacterTo(charKey: string, targetTileX: number, targetTileY: number) {
    const sprite = this.sprites.get(charKey);
    if (!sprite || this.collisionGrid.length === 0) return;
    if (this.walkingChars.has(charKey)) return; // already walking

    // Validate target is walkable
    if (
      targetTileY < 0 ||
      targetTileY >= this.collisionGrid.length ||
      targetTileX < 0 ||
      targetTileX >= this.collisionGrid[0].length
    ) {
      return;
    }
    if (this.collisionGrid[targetTileY][targetTileX] !== 0) return;

    const currentTileX = Math.floor(sprite.x / TILE_SIZE);
    const currentTileY = Math.floor((sprite.y - 1) / TILE_SIZE); // -1 because origin is bottom

    const easystar = createPathfinder(this.collisionGrid);
    easystar.findPath(
      currentTileX,
      currentTileY,
      targetTileX,
      targetTileY,
      (path: PathPoint[] | null) => {
        if (path && path.length > 1) {
          this.walkPath(charKey, path.slice(1)); // skip starting tile
        }
      },
    );
    easystar.calculate();
  }

  private walkPath(charKey: string, path: PathPoint[]) {
    const sprite = this.sprites.get(charKey);
    if (!sprite) return;

    this.walkingChars.add(charKey);
    this.walkStep(charKey, sprite, path, 0);
  }

  private walkStep(
    charKey: string,
    sprite: Phaser.GameObjects.Sprite,
    path: PathPoint[],
    index: number,
  ) {
    if (index >= path.length) {
      // Arrived — set idle frame facing down
      sprite.stop();
      sprite.setFrame(IDLE_DOWN);
      this.walkingChars.delete(charKey);
      return;
    }

    const target = path[index];
    const targetX = target.x * TILE_SIZE + TILE_SIZE / 2;
    const targetY = (target.y + 1) * TILE_SIZE;

    // Determine direction
    const dx = targetX - sprite.x;
    const dy = targetY - sprite.y;

    let animKey: string;
    if (Math.abs(dx) > Math.abs(dy)) {
      animKey = dx > 0 ? `${charKey}-walk-right` : `${charKey}-walk-left`;
    } else {
      animKey = dy > 0 ? `${charKey}-walk-down` : `${charKey}-walk-up`;
    }

    sprite.play(animKey, true);
    // Update depth based on Y for proper sorting
    sprite.setDepth(1 + target.y * 0.01);

    const distance = Math.sqrt(dx * dx + dy * dy);
    const duration = (distance / WALK_SPEED) * 1000;

    this.tweens.add({
      targets: sprite,
      x: targetX,
      y: targetY,
      duration: Math.max(duration, 50),
      ease: 'Linear',
      onComplete: () => {
        this.walkStep(charKey, sprite, path, index + 1);
      },
    });
  }

  update() {
    // EasyStar calculate is handled synchronously via createPathfinder per request
  }
}
