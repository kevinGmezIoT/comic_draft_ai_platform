import React, { useState, useEffect } from 'react';
import EditorCanvas from './components/EditorCanvas';
import { Loader2, Zap, Save, Download, Image as ImageIcon, MessageSquare, Wand2, RefreshCw } from 'lucide-react';
import axios from 'axios';

function App() {
    const [loading, setLoading] = useState(false);
    const [panels, setPanels] = useState([]);
    const [pages, setPages] = useState([]);
    const [selectedPanel, setSelectedPanel] = useState(null);
    const [maxPages, setMaxPages] = useState(3);
    const [maxPanels, setMaxPanels] = useState(6);
    const [layoutStyle, setLayoutStyle] = useState('dynamic'); // 'dynamic' | 'vertical' | 'grid'
    const [viewMode, setViewMode] = useState('draft'); // 'draft' | 'organic'
    const [error, setError] = useState(null);
    const [projectId] = useState("df81774e-5612-4c6e-88c9-5a1e8a9f6d4a");

    const fetchPanels = async () => {
        try {
            const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);
            if (response.data.pages) {
                setPages(response.data.pages);
                // Extraer todos los paneles para compatibilidad con el canvas actual
                const allPanels = response.data.pages.flatMap(p => p.panels);
                setPanels(allPanels);
            }
        } catch (error) {
            console.error("Error fetching panels:", error);
        }
    };

    useEffect(() => {
        fetchPanels();
    }, []);

    const handleGenerate = async () => {
        setLoading(true);
        setError(null);
        try {
            await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/generate/`, {
                max_pages: maxPages,
                max_panels: maxPanels,
                layout_style: layoutStyle
            });
            const interval = setInterval(async () => {
                const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);

                if (response.data.status === 'failed') {
                    setError(response.data.last_error);
                    setLoading(false);
                    clearInterval(interval);
                } else if (response.data.pages && response.data.pages.length > 0) {
                    setPages(response.data.pages);
                    const allPanels = response.data.pages.flatMap(p => p.panels);
                    setPanels(allPanels);
                    setLoading(false);
                    clearInterval(interval);
                }
            }, 3000);
        } catch (error) {
            console.error("Error generating comic:", error);
            setLoading(false);
        }
    };

    return (
        <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
            {/* Sidebar de Control */}
            <div className="w-72 bg-gray-900 border-r border-gray-800 p-6 flex flex-col gap-6 shrink-0 text-white">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
                        <Zap size={18} fill="white" />
                    </div>
                    <h1 className="text-xl font-bold">ComicDraft</h1>
                </div>

                <div className="space-y-4">
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Configuración</h2>
                    <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-800 space-y-4">
                        <div>
                            <label className="text-xs text-gray-400 block mb-2">Máximo de Páginas</label>
                            <input
                                type="number"
                                min="1" max="10"
                                value={maxPages}
                                onChange={(e) => setMaxPages(parseInt(e.target.value))}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-gray-400 block mb-2">Cantidad de Paneles</label>
                            <input
                                type="number"
                                min="1" max="20"
                                value={maxPanels}
                                onChange={(e) => setMaxPanels(parseInt(e.target.value))}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-gray-400 block mb-2">Estilo de Layout</label>
                            <select
                                value={layoutStyle}
                                onChange={(e) => setLayoutStyle(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            >
                                <option value="dynamic">Dinámico (Auto)</option>
                                <option value="vertical">Vertical (Stack)</option>
                                <option value="grid">Grid 2x2</option>
                            </select>
                        </div>
                    </div>
                </div>

                <button
                    onClick={handleGenerate}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-800 text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-lg hover:shadow-purple-500/20"
                >
                    {loading ? <Loader2 className="animate-spin" /> : <Wand2 size={18} />}
                    {loading ? "Generando..." : "Generar Borrador"}
                </button>

                <div className="space-y-4">
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Proyecto</h2>
                    <div className="bg-gray-800/50 p-4 rounded-xl border border-gray-800">
                        <p className="text-sm font-medium text-gray-300">Cyber Noir City</p>
                        <p className="text-xs text-gray-500 mt-1">ID: {projectId.slice(0, 8)}...</p>
                    </div>
                </div>

                <div className="mt-auto pt-6 border-t border-gray-800">
                    <div className="grid grid-cols-2 gap-3">
                        <button className="flex flex-col items-center gap-2 p-3 bg-gray-800/50 rounded-xl hover:bg-gray-800 border border-gray-800 transition text-gray-400 hover:text-white text-xs">
                            <Download size={18} />
                            PDF
                        </button>
                        <button className="flex items-center justify-center p-3 bg-gray-800/50 rounded-xl hover:bg-gray-800 border border-gray-800 transition text-gray-400 hover:text-white">
                            <Save size={18} />
                        </button>
                    </div>
                </div>
            </div>

            {/* Area del Editor */}
            <div className="flex-1 overflow-auto bg-gray-950 flex flex-col items-center py-10 px-6">
                {error && (
                    <div className="w-full max-w-4xl mb-6 bg-red-900/20 border border-red-500/50 p-4 rounded-xl flex items-start gap-3 animate-in fade-in slide-in-from-top-4 duration-300">
                        <div className="bg-red-500 rounded-lg p-1.5 shrink-0">
                            <Zap size={18} className="text-white" />
                        </div>
                        <div className="flex-1">
                            <h3 className="font-bold text-red-400 text-sm">Error de Generación</h3>
                            <p className="text-xs text-red-300/80 mt-1 leading-relaxed">
                                {error.includes("content_policy_violation")
                                    ? "OpenAI rechazó el prompt debido a sus políticas de seguridad. Intenta con una descripción menos explícita o diferente."
                                    : `Ocurrió un error inesperado: ${error}`}
                            </p>
                        </div>
                        <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 transition">
                            <Zap size={14} />
                        </button>
                    </div>
                )}

                <div className="mb-6 flex gap-4">
                    <div className="flex bg-gray-900 rounded-lg p-1 border border-gray-800">
                        <button
                            onClick={() => setViewMode('draft')}
                            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${viewMode === 'draft' ? 'bg-gray-800 text-white' : 'text-gray-500'}`}
                        >
                            Draft Panels
                        </button>
                        <button
                            onClick={() => setViewMode('organic')}
                            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${viewMode === 'organic' ? 'bg-gray-800 text-white' : 'text-gray-500'}`}
                        >
                            Organic Merge
                        </button>
                    </div>
                </div>

                {viewMode === 'draft' ? (
                    <EditorCanvas
                        panels={panels}
                        onSelectPanel={setSelectedPanel}
                        selectedId={selectedPanel?.id}
                    />
                ) : (
                    <div className="flex flex-col gap-8 items-center w-full max-w-4xl">
                        {pages.map(page => (
                            <div key={page.page_number} className="w-full bg-gray-900 rounded-2xl p-4 border border-gray-800">
                                <h3 className="text-xs font-bold text-gray-500 uppercase mb-4 px-2">Página {page.page_number} - Resultado Orgánico</h3>
                                {page.merged_image_url ? (
                                    <img
                                        src={page.merged_image_url}
                                        alt={`Page ${page.page_number} Merged`}
                                        className="w-full rounded-lg shadow-2xl border border-black"
                                    />
                                ) : (
                                    <div className="w-full aspect-[2/3] bg-gray-950 rounded-lg flex items-center justify-center border-2 border-dashed border-gray-800">
                                        <div className="text-center">
                                            <Loader2 className="animate-spin text-purple-500 mx-auto mb-2" />
                                            <p className="text-sm text-gray-600">Fusionando paneles...</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Inspector Panel */}
            <div className="w-80 bg-gray-900 border-l border-gray-800 flex flex-col shrink-0">
                {selectedPanel ? (
                    <div className="flex flex-col h-full p-6">
                        <div className="flex items-center justify-between mb-6">
                            <h2 className="font-bold flex items-center gap-2">
                                <ImageIcon size={18} className="text-purple-400" />
                                Panel Inspector
                            </h2>
                            <span className="text-xs bg-gray-800 px-2 py-1 rounded text-gray-400">
                                #{selectedPanel.id.slice(-4)}
                            </span>
                        </div>

                        <div className="space-y-6 flex-1 overflow-auto pr-1">
                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2">Descripción de Escena</label>
                                <p className="text-sm text-gray-400 bg-gray-950/50 p-3 rounded-xl border border-gray-800">
                                    {selectedPanel.scene_description || "Sin descripción disponible."}
                                </p>
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2">Visual Prompt</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl p-3 text-sm text-gray-300 h-24 resize-none focus:border-purple-500 outline-none"
                                    value={selectedPanel.prompt}
                                    readOnly
                                />
                            </div>

                            {selectedPanel.balloons && selectedPanel.balloons.length > 0 && (
                                <div>
                                    <label className="text-xs font-bold text-gray-500 uppercase block mb-2">Diálogos ({selectedPanel.balloons.length})</label>
                                    <div className="space-y-2">
                                        {selectedPanel.balloons.map((b, i) => (
                                            <div key={i} className="text-xs p-2 bg-gray-800/30 rounded-lg border border-gray-800">
                                                <span className="font-bold text-purple-400 mr-1">{b.character || 'Narrador'}:</span>
                                                <span className="text-gray-400 italic">"{b.text}"</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2">Acciones</label>
                                <button className="w-full flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-sm font-semibold py-2.5 px-4 rounded-xl transition border border-gray-700">
                                    <RefreshCw size={16} />
                                    Regenerar Panel
                                </button>
                            </div>

                            <div className="p-4 bg-purple-900/10 border border-purple-500/20 rounded-xl">
                                <p className="text-[10px] text-purple-400 font-bold uppercase mb-1">Tip de IA</p>
                                <p className="text-xs text-purple-300/80 leading-relaxed">
                                    Prueba a modificar los rasgos del personaje para mantener consistencia visual entre paneles.
                                </p>
                            </div>
                        </div>

                        <div className="mt-6 pt-6 border-t border-gray-800">
                            <button className="w-full py-2.5 bg-white text-black font-bold rounded-xl text-sm hover:bg-gray-200 transition">
                                Aplicar Cambios
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center p-10 text-center">
                        <div className="w-16 h-16 bg-gray-800/50 rounded-full flex items-center justify-center mb-4 border border-gray-800">
                            <ImageIcon size={24} className="text-gray-600" />
                        </div>
                        <h3 className="text-gray-400 font-medium">Sin selección</h3>
                        <p className="text-xs text-gray-600 mt-2 leading-relaxed">
                            Selecciona un panel en el lienzo para ver y editar sus especificaciones decriptivas.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
