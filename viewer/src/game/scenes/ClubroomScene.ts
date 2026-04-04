import Phaser from 'phaser';

export class ClubroomScene extends Phaser.Scene {
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
    map.createLayer('furniture', tilesets);

    // collision layer is invisible — used for pathfinding
    const collisionLayer = map.createLayer('collision', tilesets);
    if (collisionLayer) {
      collisionLayer.setVisible(false);
    }

    // Set camera bounds to map size
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
  }
}
