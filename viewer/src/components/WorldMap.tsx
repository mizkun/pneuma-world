import { useEffect, useRef } from 'react';
import Phaser from 'phaser';

export function WorldMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (gameRef.current) return; // StrictMode 二重マウント対策

    const config: Phaser.Types.Core.GameConfig = {
      type: Phaser.AUTO,
      parent: containerRef.current!,
      width: 960,   // 16px * 30tiles * 2x zoom
      height: 960,
      pixelArt: true,
      scale: {
        zoom: 2,
      },
      scene: {
        preload() {},
        create() {
          this.add.text(100, 100, 'Clubroom Scene', { color: '#fff' });
        },
      },
    };

    gameRef.current = new Phaser.Game(config);

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="w-full h-full" />;
}
