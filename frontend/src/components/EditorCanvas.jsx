import React, { useState } from 'react';
import { Stage, Layer, Rect, Image, Text, Group } from 'react-konva';
import useImage from 'use-image';

const Balloon = ({ text, x, y, type, character }) => {
  const isNarration = type === "narration";

  return (
    <Group x={x} y={y}>
      <Rect
        width={180}
        height={70}
        fill={isNarration ? "#fef3c7" : "white"}
        cornerRadius={isNarration ? 0 : 20}
        stroke="#000"
        strokeWidth={1.5}
        shadowColor="black"
        shadowBlur={4}
        shadowOpacity={0.3}
      />
      <Text
        text={text}
        width={160}
        x={10}
        y={15}
        fontSize={13}
        fontFamily="sans-serif"
        fill="black"
        align="center"
        fontStyle="bold"
      />
      {!isNarration && character && (
        <Text
          text={character.toUpperCase()}
          x={10} y={-15}
          fontSize={11}
          fontStyle="bold"
          fill="#1f2937"
          stroke="white"
          strokeWidth={0.5}
        />
      )}
    </Group>
  );
};

const PanelImage = ({ url, x, y, width, height, isSelected, onClick, balloons = [] }) => {
  const [image] = useImage(url);

  const getBalloonPos = (hint, idx) => {
    switch (hint) {
      case "top-left": return { x: x + 15, y: y + 15 + (idx * 80) };
      case "top-right": return { x: x + width - 195, y: y + 15 + (idx * 80) };
      case "bottom-center": return { x: x + (width / 2) - 90, y: y + height - 85 - (idx * 80) };
      default: return { x: x + 40, y: y + 40 + (idx * 80) };
    }
  };

  return (
    <Group onClick={onClick}>
      {image ? (
        <Image image={image} x={x} y={y} width={width} height={height} cornerRadius={8} />
      ) : (
        <Rect x={x} y={y} width={width} height={height} fill="#1e293b" cornerRadius={8} />
      )}
      <Rect
        x={x} y={y} width={width} height={height}
        stroke={isSelected ? "#8b5cf6" : "transparent"}
        strokeWidth={4} cornerRadius={8}
      />
      {balloons && balloons.map((b, i) => {
        const pos = getBalloonPos(b.position_hint, i);
        return <Balloon key={i} {...b} x={pos.x} y={pos.y} />;
      })}
    </Group>
  );
};

const EditorCanvas = ({ panels, onSelectPanel, selectedId }) => {
  const CANVAS_WIDTH = 800;
  const PAGE_HEIGHT = 1100;

  return (
    <div className="bg-gray-900 p-8 flex justify-center items-center shadow-inner rounded-2xl">
      <div className="shadow-2xl border border-gray-800 rounded-lg overflow-hidden bg-white">
        <Stage width={CANVAS_WIDTH} height={PAGE_HEIGHT * 3}>
          <Layer>{panels.map((panel, index) => {
            const pageIdx = panel.page_number - 1;
            const pageOffset = pageIdx * PAGE_HEIGHT;

            let x, y, width, height;

            if (panel.layout && panel.layout.w) {
              x = (panel.layout.x / 100) * (CANVAS_WIDTH - 40) + 20;
              y = (panel.layout.y / 100) * (PAGE_HEIGHT - 40) + 20 + pageOffset;
              width = (panel.layout.w / 100) * (CANVAS_WIDTH - 40);
              height = (panel.layout.h / 100) * (PAGE_HEIGHT - 40);
            } else {
              x = (index % 2) * 390 + 10;
              y = Math.floor(index / 2) * 410 + 10;
              width = 380;
              height = 380;
            }

            return (
              <PanelImage
                key={panel.id}
                url={panel.image_url}
                x={x} y={y}
                width={width} height={height}
                balloons={panel.balloons}
                isSelected={selectedId === panel.id}
                onClick={() => onSelectPanel(panel)}
              />
            );
          })}</Layer>
        </Stage>
      </div>
    </div>
  );
};

export default EditorCanvas;
