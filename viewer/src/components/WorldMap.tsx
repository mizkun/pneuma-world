import { useEffect, useRef } from 'react';
import Phaser from 'phaser';
import { ClubroomScene } from '../game/scenes/ClubroomScene';

export function WorldMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (gameRef.current) return; // StrictMode 二重マウント対策

    const config: Phaser.Types.Core.GameConfig = {
      type: Phaser.AUTO,
      parent: containerRef.current!,
      width: 640,   // 20 tiles * 16px * zoom 2
      height: 480,  // 15 tiles * 16px * zoom 2
      pixelArt: true,
      scale: {
        zoom: 2,
      },
      scene: [ClubroomScene],
    };

    gameRef.current = new Phaser.Game(config);

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="w-full h-full" />;
}
