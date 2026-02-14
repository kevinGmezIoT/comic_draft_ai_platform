import React, { useState, useRef, useEffect } from 'react';
import { Stage, Layer, Rect, Image, Text, Group, Transformer } from 'react-konva';
import useImage from 'use-image';

const Balloon = ({ balloon, index, x, y, width, height, fontSize, panelWidth, panelHeight, isSelected, onSelect, onChange, onDelete }) => {
  const isNarration = balloon.type === "narration";
  const groupRef = useRef();
  const textRef = useRef();

  // Use stored dimensions or defaults
  const bWidth = width || Math.min(180, panelWidth * 0.8);
  const bHeight = height || 70;
  const bFontSize = fontSize || 13;

  return (
    <Group
      ref={groupRef}
      x={x}
      y={y}
      draggable
      onClick={(e) => { e.cancelBubble = true; onSelect(); }}
      onTap={(e) => { e.cancelBubble = true; onSelect(); }}
      onDragStart={(e) => { e.cancelBubble = true; }}
      onDragMove={(e) => { e.cancelBubble = true; }}
      onDragEnd={(e) => {
        e.cancelBubble = true;
        onChange({
          ...balloon,
          x: e.target.x(),
          y: e.target.y(),
          width: bWidth,
          height: bHeight,
          fontSize: bFontSize
        });
      }}
    >
      <Rect
        width={bWidth}
        height={bHeight}
        fill={isNarration ? "#fef3c7" : "white"}
        cornerRadius={isNarration ? 0 : 20}
        stroke={isSelected ? "#8b5cf6" : "#000"}
        strokeWidth={isSelected ? 2.5 : 1.5}
        shadowColor="black"
        shadowBlur={4}
        shadowOpacity={0.3}
      />
      <Text
        ref={textRef}
        text={balloon.text}
        width={bWidth - 20}
        x={10}
        y={12}
        fontSize={bFontSize}
        fontFamily="sans-serif"
        fill="black"
        align="center"
        fontStyle="bold"
        wrap="word"
        ellipsis={true}
        height={bHeight - 24}
      />
      {!isNarration && balloon.character && (
        <Text
          text={balloon.character.toUpperCase()}
          x={10} y={-15}
          fontSize={11}
          fontStyle="bold"
          fill="#1f2937"
          stroke="white"
          strokeWidth={0.5}
        />
      )}
      {/* Delete handle visible on selection */}
      {isSelected && (
        <Group
          x={bWidth - 8}
          y={-8}
          onClick={(e) => { e.cancelBubble = true; onDelete(); }}
          onTap={(e) => { e.cancelBubble = true; onDelete(); }}
        >
          <Rect width={18} height={18} fill="#ef4444" cornerRadius={9} />
          <Text text="×" x={3} y={0} fontSize={14} fill="white" fontStyle="bold" />
        </Group>
      )}
      {/* Resize handle visible on selection */}
      {isSelected && (
        <Rect
          x={bWidth - 10}
          y={bHeight - 10}
          width={10}
          height={10}
          fill="#8b5cf6"
          cornerRadius={2}
          draggable
          onDragStart={(e) => { e.cancelBubble = true; }}
          onDragMove={(e) => { e.cancelBubble = true; }}
          onDragEnd={(e) => {
            e.cancelBubble = true;
            const node = e.target;
            // node.x()/y() is the absolute position within the group, not the delta.
            // Subtract original handle position to get the actual drag offset.
            const deltaX = node.x() - (bWidth - 10);
            const deltaY = node.y() - (bHeight - 10);
            // Reset handle position back to its original spot relative to the group
            node.x(bWidth - 10);
            node.y(bHeight - 10);
            const newW = Math.max(80, bWidth + deltaX);
            const newH = Math.max(40, bHeight + deltaY);
            onChange({
              ...balloon,
              x: groupRef.current.x(),
              y: groupRef.current.y(),
              width: newW,
              height: newH,
              fontSize: bFontSize
            });
          }}
        />
      )}
    </Group>
  );
};

const BalloonDefaults = {
  getPosition: (hint, idx, panelWidth, panelHeight) => {
    switch (hint) {
      case "top-left": return { x: 15, y: 15 + (idx * 80) };
      case "top-right": return { x: panelWidth - 195, y: 15 + (idx * 80) };
      case "top-center": return { x: (panelWidth / 2) - 90, y: 15 + (idx * 80) };
      case "bottom-center": return { x: (panelWidth / 2) - 90, y: panelHeight - 85 - (idx * 80) };
      case "bottom-left": return { x: 15, y: panelHeight - 85 - (idx * 80) };
      case "bottom-right": return { x: panelWidth - 195, y: panelHeight - 85 - (idx * 80) };
      default: return { x: 40, y: 40 + (idx * 80) };
    }
  }
};

const PanelImage = ({
  panel, x, y, width, height, isSelected, onSelect, onLayoutChange,
  selectedBalloonKey, onSelectBalloon, onBalloonChange, onDeleteBalloon, onSelectPanel
}) => {
  const [image] = useImage(panel.image_url);
  const shapeRef = useRef();

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
      {/* Selection highlight */}
      <Rect
        width={width}
        height={height}
        stroke={isSelected ? "#8b5cf6" : "transparent"}
        strokeWidth={2}
        cornerRadius={8}
        listening={false}
      />
      {/* Balloons */}
      {panel.balloons && panel.balloons.map((b, i) => {
        // Use stored position or calculate from hint
        const hasStoredPos = b.x !== undefined && b.y !== undefined;
        const pos = hasStoredPos
          ? { x: b.x, y: b.y }
          : BalloonDefaults.getPosition(b.position_hint, i, width, height);

        const balloonKey = `${panel.id}-${i}`;

        return (
          <Balloon
            key={i}
            balloon={b}
            index={i}
            x={pos.x}
            y={pos.y}
            width={b.width}
            height={b.height}
            fontSize={b.fontSize}
            panelWidth={width}
            panelHeight={height}
            isSelected={selectedBalloonKey === balloonKey}
            onSelect={() => { onSelectPanel(); onSelectBalloon(balloonKey); }}
            onChange={(updated) => onBalloonChange(panel.id, i, updated)}
            onDelete={() => onDeleteBalloon(panel.id, i)}
          />
        );
      })}
    </Group>
  );
};

const EditorCanvas = ({ panels, onSelectPanel, selectedId, onUpdateLayout, currentPage, dimensions, onDeletePanel, onBalloonChange, onDeleteBalloon }) => {
  const CANVAS_WIDTH = dimensions?.w || 800;
  const PAGE_HEIGHT = dimensions?.h || 1100;
  const transformerRef = useRef();
  const stageRef = useRef();
  const [selectedBalloonKey, setSelectedBalloonKey] = useState(null);

  // Filter panels to only show the ones for the current page
  const pagePanels = panels.filter(p => p.page_number === currentPage);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

        // If a balloon is selected, delete it instead of the panel
        if (selectedBalloonKey) {
          const [panelId, bIdx] = selectedBalloonKey.split('-');
          onDeleteBalloon(parseInt(panelId) || panelId, parseInt(bIdx));
          setSelectedBalloonKey(null);
          return;
        }
        onDeletePanel(selectedId);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedId, selectedBalloonKey, onDeletePanel, onDeleteBalloon]);

  useEffect(() => {
    if (selectedId && transformerRef.current) {
      const selectedNode = stageRef.current.findOne('.' + selectedId);
      if (selectedNode) {
        transformerRef.current.nodes([selectedNode]);
        transformerRef.current.getLayer().batchDraw();
      }
    }
  }, [selectedId, currentPage]);

  const handleLayoutChange = (panel, newLayoutPx) => {
    const px_w = newLayoutPx.w_px || (panel.layout?.w / 100 * (CANVAS_WIDTH - 40)) || 370;
    const px_h = newLayoutPx.h_px || (panel.layout?.h / 100 * (PAGE_HEIGHT - 40)) || 370;

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
            if (clickedOnEmpty) {
              onSelectPanel(null);
              setSelectedBalloonKey(null);
            }
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
                  onSelect={() => { onSelectPanel(panel); setSelectedBalloonKey(null); }}
                  onLayoutChange={(newLayoutPx) => handleLayoutChange(panel, newLayoutPx)}
                  selectedBalloonKey={selectedBalloonKey}
                  onSelectBalloon={setSelectedBalloonKey}
                  onBalloonChange={onBalloonChange}
                  onDeleteBalloon={onDeleteBalloon}
                  onSelectPanel={() => onSelectPanel(panel)}
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
