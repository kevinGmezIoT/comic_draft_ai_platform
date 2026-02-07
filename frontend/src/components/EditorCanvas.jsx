import React, { useState, useRef, useEffect } from 'react';
import { Stage, Layer, Rect, Image, Text, Group, Transformer } from 'react-konva';
import useImage from 'use-image';

const Balloon = ({ text, x, y, type, character, panelWidth }) => {
  const isNarration = type === "narration";
  const width = Math.min(180, panelWidth * 0.8);

  return (
    <Group x={x} y={y}>
      <Rect
        width={width}
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
        width={width - 20}
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

const PanelImage = ({
  panel, x, y, width, height, isSelected, onSelect, onLayoutChange
}) => {
  const [image] = useImage(panel.image_url);
  const shapeRef = useRef();

  const getBalloonPos = (hint, idx) => {
    switch (hint) {
      case "top-left": return { x: 15, y: 15 + (idx * 80) };
      case "top-right": return { x: width - 195, y: 15 + (idx * 80) };
      case "bottom-center": return { x: (width / 2) - 90, y: height - 85 - (idx * 80) };
      default: return { x: 40, y: 40 + (idx * 80) };
    }
  };

  return (
    <Group
      x={x}
      y={y}
      width={width}
      height={height}
      name={String(panel.id)}
      draggable
      onClick={onSelect}
      onTap={onSelect}
      ref={shapeRef}
      onDragEnd={(e) => {
        onLayoutChange({
          ...panel.layout,
          x_px: e.target.x(),
          y_px: e.target.y(),
          w_px: width,
          h_px: height
        });
      }}
      onTransformEnd={(e) => {
        const node = shapeRef.current;
        const scaleX = node.scaleX();
        const scaleY = node.scaleY();

        node.scaleX(1);
        node.scaleY(1);

        onLayoutChange({
          ...panel.layout,
          x_px: node.x(),
          y_px: node.y(),
          w_px: Math.abs(width * scaleX),
          h_px: Math.abs(height * scaleY),
        });
      }}
    >
      {image ? (
        <Image
          image={image}
          width={width}
          height={height}
          cornerRadius={8}
        />
      ) : (
        <Group>
          <Rect
            width={width}
            height={height}
            fill="#0f172a"
            cornerRadius={8}
            stroke="#334155"
            strokeWidth={1}
            dash={[10, 5]}
          />
          <Text
            text={`PANEL ${panel.order + 1}`}
            width={width}
            height={height}
            align="center"
            verticalAlign="middle"
            fill="#475569"
            fontSize={14}
            fontStyle="bold"
            fontFamily="sans-serif"
          />
        </Group>
      )}
      {/* Selection highlight (Transformer already shows a box, but this adds a glow) */}
      <Rect
        width={width}
        height={height}
        stroke={isSelected ? "#8b5cf6" : "transparent"}
        strokeWidth={2}
        cornerRadius={8}
        listening={false}
      />
      {panel.balloons && panel.balloons.map((b, i) => {
        const pos = getBalloonPos(b.position_hint, i);
        return <Balloon key={i} {...b} x={pos.x} y={pos.y} panelWidth={width} />;
      })}
    </Group>
  );
};

const EditorCanvas = ({ panels, onSelectPanel, selectedId, onUpdateLayout, currentPage, dimensions, onDeletePanel }) => {
  const CANVAS_WIDTH = dimensions?.w || 800;
  const PAGE_HEIGHT = dimensions?.h || 1100;
  const transformerRef = useRef();
  const stageRef = useRef();

  // Filter panels to only show the ones for the current page
  const pagePanels = panels.filter(p => p.page_number === currentPage);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        // Only delete if the user is not typing in a textarea/input
        if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
        onDeletePanel(selectedId);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedId, onDeletePanel]);

  useEffect(() => {
    if (selectedId && transformerRef.current) {
      const selectedNode = stageRef.current.findOne('.' + selectedId);
      if (selectedNode) {
        transformerRef.current.nodes([selectedNode]);
        transformerRef.current.getLayer().batchDraw();
      }
    }
  }, [selectedId, currentPage]); // Re-bind on page change

  const handleLayoutChange = (panel, newLayoutPx) => {
    // Safety check for dimensions
    const px_w = newLayoutPx.w_px || (panel.layout?.w / 100 * (CANVAS_WIDTH - 40)) || 370;
    const px_h = newLayoutPx.h_px || (panel.layout?.h / 100 * (PAGE_HEIGHT - 40)) || 370;

    // Convert pixels back to relative percentages for persistence
    const newLayout = {
      ...panel.layout,
      x: ((newLayoutPx.x_px - 20) / (CANVAS_WIDTH - 40)) * 100,
      y: ((newLayoutPx.y_px - 20) / (PAGE_HEIGHT - 40)) * 100,
      w: (px_w / (CANVAS_WIDTH - 40)) * 100,
      h: (px_h / (PAGE_HEIGHT - 40)) * 100
    };

    onUpdateLayout(panel.id, newLayout);
  };

  return (
    <div className="bg-gray-900 p-8 flex justify-center items-center shadow-inner rounded-2xl w-full select-none overflow-auto">
      <div className="shadow-2xl border border-gray-800 rounded-lg overflow-hidden bg-white transition-all duration-300">
        <Stage
          width={CANVAS_WIDTH}
          height={PAGE_HEIGHT}
          ref={stageRef}
          onMouseDown={(e) => {
            const clickedOnEmpty = e.target === e.target.getStage();
            if (clickedOnEmpty) onSelectPanel(null);
          }}
        >
          <Layer>
            {pagePanels.map((panel) => {
              const layout = panel.layout || {};
              const x = (layout.x || 0) / 100 * (CANVAS_WIDTH - 40) + 20;
              const y = (layout.y || 0) / 100 * (PAGE_HEIGHT - 40) + 20;
              const width = (layout.w || 30) / 100 * (CANVAS_WIDTH - 40);
              const height = (layout.h || 30) / 100 * (PAGE_HEIGHT - 40);

              return (
                <PanelImage
                  key={panel.id}
                  panel={panel}
                  x={x} y={y}
                  width={width} height={height}
                  isSelected={selectedId === panel.id}
                  onSelect={() => onSelectPanel(panel)}
                  onLayoutChange={(newLayoutPx) => handleLayoutChange(panel, newLayoutPx)}
                />
              );
            })}
            {selectedId && (
              <Transformer
                ref={transformerRef}
                rotateEnabled={false}
                flipEnabled={false}
                enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right', 'middle-left', 'middle-right', 'bottom-center', 'top-center']}
                padding={2}
                ignoreStroke={true}
                boundBoxFunc={(oldBox, newBox) => {
                  if (Math.abs(newBox.width) < 50 || Math.abs(newBox.height) < 50) return oldBox;
                  return newBox;
                }}
              />
            )}
          </Layer>
        </Stage>
      </div>
    </div>
  );
};

export default EditorCanvas;
