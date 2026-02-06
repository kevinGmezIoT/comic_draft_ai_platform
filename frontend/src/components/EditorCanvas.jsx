import React, { useState } from 'react';
import { Stage, Layer, Rect, Image, Text } from 'react-konva';
import useImage from 'use-image';

const PanelImage = ({ url, x, y, width, height }) => {
  const [image] = useImage(url);
  if (!image) {
    return <Rect x={x} y={y} width={width} height={height} fill="#f1f5f9" cornerRadius={10} />;
  }
  return <Image image={image} x={x} y={y} width={width} height={height} cornerRadius={10} />;
};

const EditorCanvas = ({ panels }) => {
  const [selectedId, setSelectedId] = useState(null);

  return (
    <div className="bg-gray-900 p-8 flex justify-center items-center min-h-screen">
      <div className="shadow-2xl border border-gray-700 rounded-lg overflow-hidden bg-white">
        <Stage width={800} height={1100}>
          <Layer>
            {panels.map((panel, index) => {
              // Layout simple de rejilla para el prototipo
              const x = (index % 2) * 390 + 10;
              const y = Math.floor(index / 2) * 350 + 10;

              return (
                <React.Fragment key={panel.id}>
                  {panel.image_url ? (
                    <PanelImage
                      url={panel.image_url}
                      x={x} y={y}
                      width={380} height={340}
                    />
                  ) : (
                    <Rect
                      x={x} y={y}
                      width={380} height={340}
                      fill="#e2e8f0"
                      stroke="#cbd5e1"
                      cornerRadius={10}
                    />
                  )}
                  <Text
                    text={`Panel ${index + 1}`}
                    x={x + 10} y={y + 310}
                    fill="#475569"
                    fontSize={14}
                  />
                </React.Fragment>
              );
            })}
          </Layer>
        </Stage>
      </div>
    </div>
  );
};

export default EditorCanvas;
