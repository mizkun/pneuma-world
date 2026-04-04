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
  displayName: string;
  spriteFile: string;
  startTileX: number;
  startTileY: number;
}

const CHARACTERS: CharacterDef[] = [
  { key: 'aoi', displayName: '葵', spriteFile: 'Premade_Character_01.png', startTileX: 7, startTileY: 8 },
  { key: 'rin', displayName: '凛', spriteFile: 'Premade_Character_02.png', startTileX: 9, startTileY: 6 },
  { key: 'hinata', displayName: 'ひなた', spriteFile: 'Premade_Character_03.png', startTileX: 11, startTileY: 8 },
];

const TILE_SIZE = 16;
const WALK_SPEED = 80; // pixels per second

/** Speech bubble container for cleanup */
interface SpeechBubble {
  graphics: Phaser.GameObjects.Graphics;
  text: Phaser.GameObjects.Text;
  timer?: Phaser.Time.TimerEvent;
}

export class ClubroomScene extends Phaser.Scene {
  private sprites: Map<string, Phaser.GameObjects.Sprite> = new Map();
  private nameLabels: Map<string, Phaser.GameObjects.Text> = new Map();
  private speechBubbles: Map<string, SpeechBubble> = new Map();
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

    // Debug: click character for speech bubble, click elsewhere to move aoi
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      const worldPoint = this.cameras.main.getWorldPoint(pointer.x, pointer.y);

      // Check if a character sprite was clicked
      for (const [key, sprite] of this.sprites.entries()) {
        const bounds = sprite.getBounds();
        if (bounds.contains(worldPoint.x, worldPoint.y)) {
          this.showSpeechBubble(key, 'こんにちは！テスト発言です');
          return;
        }
      }

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
      sprite.setInteractive(); // enable click detection
      this.sprites.set(char.key, sprite);

      // Name label below character
      const nameLabel = this.add.text(x, y + 2, char.displayName, {
        fontSize: '8px',
        color: '#ffffff',
        stroke: '#000000',
        strokeThickness: 2,
        align: 'center',
      });
      nameLabel.setOrigin(0.5, 0);
      nameLabel.setDepth(furnitureDepth + 2);
      this.nameLabels.set(char.key, nameLabel);
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

  /**
   * Show a speech bubble above a character sprite.
   */
  showSpeechBubble(characterKey: string, text: string) {
    const sprite = this.sprites.get(characterKey);
    if (!sprite) return;

    // Remove existing bubble for this character
    this.removeSpeechBubble(characterKey);

    // Truncate text to 40 chars
    const displayText = text.length > 40 ? text.slice(0, 40) + '...' : text;

    // Create text object to measure dimensions
    const bubbleText = this.add.text(0, 0, displayText, {
      fontSize: '8px',
      color: '#000000',
      wordWrap: { width: 100 },
      align: 'center',
    });
    bubbleText.setOrigin(0.5, 1);

    const padding = 4;
    const bubbleWidth = bubbleText.width + padding * 2;
    const bubbleHeight = bubbleText.height + padding * 2;
    const tailHeight = 4;

    // Position bubble above character
    const bubbleX = sprite.x;
    const bubbleY = sprite.y - sprite.height - tailHeight - bubbleHeight / 2;

    bubbleText.setPosition(bubbleX, bubbleY + bubbleHeight / 2 - padding);

    // Draw bubble background
    const graphics = this.add.graphics();
    const cornerRadius = 3;
    const rectX = bubbleX - bubbleWidth / 2;
    const rectY = bubbleY - bubbleHeight / 2;

    graphics.fillStyle(0xffffff, 1);
    graphics.fillRoundedRect(rectX, rectY, bubbleWidth, bubbleHeight, cornerRadius);

    // Draw tail (small triangle pointing down)
    graphics.fillTriangle(
      bubbleX - 3, rectY + bubbleHeight,
      bubbleX + 3, rectY + bubbleHeight,
      bubbleX, rectY + bubbleHeight + tailHeight,
    );

    // Stroke outline
    graphics.lineStyle(1, 0x000000, 0.3);
    graphics.strokeRoundedRect(rectX, rectY, bubbleWidth, bubbleHeight, cornerRadius);

    const bubbleDepth = sprite.depth + 10;
    graphics.setDepth(bubbleDepth);
    bubbleText.setDepth(bubbleDepth + 1);

    // Calculate display duration: 3s base + 1s per 10 chars, max 8s
    const duration = Math.min(3000 + Math.floor(displayText.length / 10) * 1000, 8000);

    // Schedule fade out
    const timer = this.time.delayedCall(duration - 500, () => {
      this.tweens.add({
        targets: [graphics, bubbleText],
        alpha: 0,
        duration: 500,
        onComplete: () => {
          this.removeSpeechBubble(characterKey);
        },
      });
    });

    this.speechBubbles.set(characterKey, { graphics, text: bubbleText, timer });
  }

  private removeSpeechBubble(characterKey: string) {
    const bubble = this.speechBubbles.get(characterKey);
    if (bubble) {
      bubble.timer?.remove();
      bubble.graphics.destroy();
      bubble.text.destroy();
      this.speechBubbles.delete(characterKey);
    }
  }

  update() {
    // Make name labels and speech bubbles follow their sprites
    for (const [key, sprite] of this.sprites.entries()) {
      const label = this.nameLabels.get(key);
      if (label) {
        label.setPosition(sprite.x, sprite.y + 2);
      }

      const bubble = this.speechBubbles.get(key);
      if (bubble) {
        const tailHeight = 4;
        const bubbleHeight = bubble.text.height + 8; // padding*2
        const bubbleWidth = bubble.text.width + 8;
        const bubbleX = sprite.x;
        const bubbleY = sprite.y - sprite.height - tailHeight - bubbleHeight / 2;

        bubble.text.setPosition(bubbleX, bubbleY + bubbleHeight / 2 - 4);

        // Redraw graphics at new position
        bubble.graphics.clear();
        const rectX = bubbleX - bubbleWidth / 2;
        const rectY = bubbleY - bubbleHeight / 2;

        bubble.graphics.fillStyle(0xffffff, 1);
        bubble.graphics.fillRoundedRect(rectX, rectY, bubbleWidth, bubbleHeight, 3);
        bubble.graphics.fillTriangle(
          bubbleX - 3, rectY + bubbleHeight,
          bubbleX + 3, rectY + bubbleHeight,
          bubbleX, rectY + bubbleHeight + tailHeight,
        );
        bubble.graphics.lineStyle(1, 0x000000, 0.3);
        bubble.graphics.strokeRoundedRect(rectX, rectY, bubbleWidth, bubbleHeight, 3);
      }
    }
  }
}
