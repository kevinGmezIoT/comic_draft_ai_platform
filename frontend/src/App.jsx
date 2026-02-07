import React, { useState, useEffect } from 'react';
import EditorCanvas from './components/EditorCanvas';
import ProjectWizard from './components/ProjectWizard';
import ProjectDashboard from './components/ProjectDashboard';
import {
    Loader2, Zap, Save, Download, Image as ImageIcon,
    MessageSquare, Wand2, RefreshCw, Plus, LayoutGrid, ChevronLeft, ChevronRight
} from 'lucide-react';
import axios from 'axios';

function App() {
    const [view, setView] = useState('dashboard'); // 'wizard' | 'dashboard' | 'editor'
    const [loading, setLoading] = useState(false);
    const [projects, setProjects] = useState([]); // Dynamic project list
    const [panels, setPanels] = useState([]);
    const [pages, setPages] = useState([]);
    const [selectedPanel, setSelectedPanel] = useState(null);
    const [maxPages, setMaxPages] = useState(3);
    const [maxPanels, setMaxPanels] = useState(6);
    const [maxPanelsPerPage, setMaxPanelsPerPage] = useState(4);
    const [layoutStyle, setLayoutStyle] = useState('dynamic');
    const [pageFormat, setPageFormat] = useState('A4'); // A4, Square, Widescreen
    const [currentPage, setCurrentPage] = useState(1);

    // Derived values for canvas
    const getCanvasDimensions = () => {
        switch (pageFormat) {
            case 'Square': return { w: 800, h: 800 };
            case 'Widescreen': return { w: 1000, h: 600 };
            default: return { w: 800, h: 1100 }; // A4
        }
    };
    const [viewMode, setViewMode] = useState('draft');
    const [error, setError] = useState(null);
    const [projectId, setProjectId] = useState(null);
    const [editingPrompt, setEditingPrompt] = useState("");
    const [editingDescription, setEditingDescription] = useState("");
    const [editingBalloons, setEditingBalloons] = useState([]);
    const [mergeInstructions, setMergeInstructions] = useState("");
    const [saving, setSaving] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const isUpdatingLayout = React.useRef(false);
    const pollingInterval = React.useRef(null);
    const [pollingRetryCount, setPollingRetryCount] = useState(0);

    const fetchProjects = async () => {
        try {
            const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/`);
            setProjects(response.data);
            if (response.data.length > 0 && !projectId) {
                setProjectId(response.data[0].id);
            }
        } catch (error) {
            console.error("Error fetching projects:", error);
        }
    };

    const fetchProjectData = async () => {
        if (!projectId) return;
        try {
            const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);
            if (response.data.pages) {
                setPages(response.data.pages);
                const allPanels = response.data.pages.flatMap(p => p.panels);
                setPanels(allPanels);
            }
        } catch (error) {
            console.error("Error fetching project:", error);
        }
    };

    useEffect(() => {
        fetchProjects();
    }, []);

    useEffect(() => {
        if (projectId && (view === 'editor' || view === 'dashboard')) {
            fetchProjectData();
        }
    }, [projectId, view]);

    useEffect(() => {
        if (selectedPanel) {
            setEditingPrompt(selectedPanel.prompt || "");
            setEditingDescription(selectedPanel.scene_description || "");
            setEditingBalloons(selectedPanel.balloons || []);
        }
    }, [selectedPanel]);

    const handleGenerate = async (settings = {}) => {
        setLoading(true);
        setError(null);

        // Map existing panels for the agent payload
        const existingPanels = panels.map(p => ({
            id: p.id,
            page_number: p.page_number,
            order_in_page: p.order,
            layout: p.layout,
            prompt: p.prompt,
            scene_description: p.scene_description
        }));

        // If we are starting from scratch or regeneration, clear local state
        if (!settings.skip_agent && !settings.skip_cleaning) {
            setPanels([]);
            setPages([]);
        }

        // Synchronize local states with dashboard settings
        if (settings.max_pages) setMaxPages(settings.max_pages);
        if (settings.max_panels) setMaxPanels(settings.max_panels);
        if (settings.max_panels_per_page) setMaxPanelsPerPage(settings.max_panels_per_page);
        if (settings.layout_style) setLayoutStyle(settings.layout_style);

        const config = {
            max_pages: settings.max_pages || maxPages,
            max_panels: settings.max_panels || maxPanels,
            max_panels_per_page: settings.max_panels_per_page || maxPanelsPerPage,
            layout_style: settings.layout_style || layoutStyle,
            plan_only: settings.plan_only || false,
            page_number: settings.page_number,
            panels: (settings.skip_agent || settings.skip_cleaning) ? existingPanels : []
        };

        try {
            // Switch to editor immediately
            setView('editor');
            if (settings.plan_only) setViewMode('draft');

            if (settings.skip_agent) {
                // No need to call generate, just ensure we have data
                setLoading(false);
                return;
            }

            const response = await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/generate/`, config);

            // If the response is already completed (Sync Path), fetch data immediately
            if (response.data && response.data.status === 'completed') {
                await fetchProjectData();
                setLoading(false);
                return;
            }

            startPollingStatus();
        } catch (error) {
            console.error("Error generating comic:", error);
            setError("Error al iniciar la generación.");
            setLoading(false);
        }
    };

    const handleDeletePanel = async (panelId) => {
        try {
            await axios.delete(`${import.meta.env.VITE_API_URL}/panels/${panelId}/`);
            await fetchProjectData();
            setSelectedPanel(null);
        } catch (error) {
            console.error("Error deleting panel:", error);
        }
    };

    const handleUpdateLayout = async (panelId, newLayout) => {
        isUpdatingLayout.current = true;
        try {
            // Optimistic update for both panels and pages
            setPanels(prev => prev.map(p => p.id === panelId ? { ...p, layout: newLayout } : p));
            setPages(prev => prev.map(page => ({
                ...page,
                panels: page.panels.map(p => p.id === panelId ? { ...p, layout: newLayout } : p)
            })));

            await axios.patch(`${import.meta.env.VITE_API_URL}/panels/${panelId}/update-layout/`, {
                layout: newLayout
            });
        } catch (error) {
            console.error("Error updating layout:", error);
        } finally {
            // Debounce the polling resume to give backend time to settle
            setTimeout(() => {
                isUpdatingLayout.current = false;
            }, 1000);
        }
    };

    const startPollingStatus = () => {
        // Clear any existing global interval before starting a new one
        if (pollingInterval.current) {
            clearInterval(pollingInterval.current);
            pollingInterval.current = null;
        }

        setPollingRetryCount(0); // Reset retry counter
        fetchProjectData(); // Immediate fetch to avoid empty state

        pollingInterval.current = setInterval(async () => {
            if (isUpdatingLayout.current) return;

            try {
                const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);

                if (response.data.status === 'failed') {
                    setError(response.data.last_error);
                    setLoading(false);
                    setRegenerating(false);
                    if (pollingInterval.current) {
                        clearInterval(pollingInterval.current);
                        pollingInterval.current = null;
                    }
                } else if (response.data.status === 'completed') {
                    if (response.data.pages && response.data.pages.length > 0) {
                        setPages(response.data.pages);
                        const allPanels = response.data.pages.flatMap(p => p.panels);
                        setPanels(allPanels);
                        if (selectedPanel) {
                            const updated = allPanels.find(p => p.id === selectedPanel.id);
                            if (updated) setSelectedPanel(updated);
                        }
                        setLoading(false);
                        setRegenerating(false);
                        if (pollingInterval.current) {
                            clearInterval(pollingInterval.current);
                            pollingInterval.current = null;
                        }
                    } else {
                        // Logic for waiting for pages if it was marked completed prematurely
                        setPollingRetryCount(prev => {
                            if (prev >= 10) { // Max 10 retires (approx 30s)
                                setError("La generación se completó pero no se encontraron paneles. Intenta regenerar.");
                                setLoading(false);
                                if (pollingInterval.current) {
                                    clearInterval(pollingInterval.current);
                                    pollingInterval.current = null;
                                }
                                return prev;
                            }
                            console.log("Status is completed but no pages found. Retry:", prev + 1);
                            return prev + 1;
                        });
                    }
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, 3000);
    };

    // Render Logic
    if (view === 'wizard') {
        return (
            <div className="flex bg-gray-950 min-h-screen items-center justify-center p-10">
                <ProjectWizard onComplete={(id) => {
                    setProjectId(id);
                    setView('dashboard');
                    fetchProjects(); // Refresh sidebar
                }} />
            </div>
        );
    }

    if (view === 'dashboard') {
        return (
            <div className="flex bg-gray-950 min-h-screen text-white">
                <div className="w-72 bg-gray-900 border-r border-gray-800 p-6 flex flex-col gap-6 shrink-0">
                    <div className="flex items-center gap-2 mb-4">
                        <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
                            <Zap size={18} fill="white" />
                        </div>
                        <h1 className="text-xl font-bold">ComicDraft AI</h1>
                    </div>
                    <button
                        onClick={() => setView('wizard')}
                        className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 text-white font-semibold py-3 px-4 rounded-xl transition-all border border-gray-700"
                    >
                        <Plus size={18} />
                        Nuevo Proyecto
                    </button>
                    <div className="space-y-4 overflow-auto pb-4">
                        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Recientes</h2>
                        <div className="space-y-2">
                            {projects.map(p => (
                                <button
                                    key={p.id}
                                    onClick={() => {
                                        setProjectId(p.id);
                                        setView('dashboard');
                                    }}
                                    className={`w-full text-left p-4 rounded-xl transition-all border ${projectId === p.id
                                        ? 'bg-purple-600/10 border-purple-500/50'
                                        : 'bg-gray-800/20 border-gray-800 hover:border-gray-700'
                                        }`}
                                >
                                    <p className={`text-sm font-bold ${projectId === p.id ? 'text-purple-400' : 'text-gray-300'}`}>
                                        {p.name}
                                    </p>
                                    <p className={`text-[10px] uppercase font-bold mt-1 ${p.status === 'completed' ? 'text-green-500' :
                                        p.status === 'failed' ? 'text-red-500' : 'text-yellow-500'
                                        }`}>
                                        {p.status}
                                    </p>
                                </button>
                            ))}
                            {projects.length === 0 && (
                                <p className="text-xs text-gray-600 text-center py-4 italic">No hay proyectos aún.</p>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex-1 overflow-auto p-12 flex flex-col items-center">
                    <ProjectDashboard
                        projectId={projectId}
                        onStartGeneration={(settings) => handleGenerate(settings)}
                    />
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
            {/* Sidebar de Control */}
            <div className="w-72 bg-gray-900 border-r border-gray-800 p-6 flex flex-col gap-6 shrink-0 text-white">
                <button
                    onClick={() => setView('dashboard')}
                    className="flex items-center gap-2 text-gray-500 hover:text-white transition-colors mb-2 text-sm font-bold"
                >
                    <ChevronLeft size={16} />
                    Volver al Tablero
                </button>
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
                        <Zap size={18} fill="white" />
                    </div>
                    <h1 className="text-lg font-bold">Editor de Cómic</h1>
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
                            <label className="text-xs text-gray-400 block mb-2">Paneles por Página</label>
                            <select
                                value={maxPanelsPerPage}
                                onChange={(e) => setMaxPanelsPerPage(parseInt(e.target.value))}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            >
                                <option value={1}>1 Panel</option>
                                <option value={2}>2 Paneles</option>
                                <option value={3}>3 Paneles</option>
                                <option value={4}>4 Paneles</option>
                                <option value={5}>5 Paneles</option>
                                <option value={6}>6 Paneles</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-gray-400 block mb-2">Formato de Página</label>
                            <select
                                value={pageFormat}
                                onChange={(e) => setPageFormat(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            >
                                <option value="A4">A4 Vertical (Estándar)</option>
                                <option value="Square">Cuadrado (Instagram)</option>
                                <option value="Widescreen">Panorámico (Cine)</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-gray-400 block mb-2">Estilo de Layout</label>
                            <select
                                value={layoutStyle}
                                onChange={(e) => setLayoutStyle(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-purple-500 outline-none"
                            >
                                <option value="dynamic">Dinámico (Creativo)</option>
                                <option value="grid">Grilla (Clásico)</option>
                                <option value="vertical">Vertical (Webtoon)</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div className="space-y-3">
                    <button
                        onClick={() => handleGenerate({ plan_only: true, page_number: currentPage })}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-3 bg-gray-800 hover:bg-gray-700 text-purple-400 font-bold py-3 rounded-xl transition-all border border-purple-900/30 active:scale-95"
                    >
                        {loading && !panels.some(p => p.image_url) ? <Loader2 className="animate-spin" /> : <RefreshCw size={18} />}
                        Regenerar Página {currentPage}
                    </button>

                    <button
                        onClick={() => handleGenerate({ plan_only: true })}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-3 bg-gray-800 hover:bg-gray-700 text-gray-400 font-bold py-3 rounded-xl transition-all border border-gray-700 active:scale-95"
                    >
                        {loading && !panels.some(p => p.image_url) ? <Loader2 className="animate-spin" /> : <LayoutGrid size={18} />}
                        Regenerar Todo (Layout)
                    </button>

                    <button
                        onClick={() => handleGenerate()}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:from-gray-800 disabled:to-gray-800 text-white font-black py-4 rounded-xl transition-all shadow-xl hover:shadow-purple-500/20 active:scale-95"
                    >
                        {loading && panels.some(p => p.image_url) ? <Loader2 className="animate-spin" /> : <Zap size={18} fill="white" />}
                        {loading ? "Generando..." : panels.every(p => !p.image_url) ? "Generar Arte IA" : "Regenerar Todo"}
                    </button>
                </div>

                <div className="mt-auto pt-6 border-t border-gray-800">
                    <div className="bg-gray-950/50 p-4 rounded-xl border border-gray-800/50 text-center">
                        <p className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Modo Borrador Editable</p>
                        <p className="text-[9px] text-gray-700 mt-1 uppercase font-bold">Ajusta el layout antes de la fusión</p>
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
                            <h3 className="font-bold text-red-400 text-sm">Error en la creación</h3>
                            <p className="text-xs text-red-300/80 mt-1">{error}</p>
                        </div>
                    </div>
                )}

                <div className="mb-6 flex items-center gap-6">
                    <div className="flex bg-gray-900 rounded-lg p-1 border border-gray-800 shadow-xl">
                        <button
                            onClick={() => setViewMode('draft')}
                            className={`px-6 py-2 rounded-md text-sm font-bold transition-all ${viewMode === 'draft' ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/20' : 'text-gray-500 hover:text-gray-300'}`}
                        >
                            Paneles (Storyline)
                        </button>
                        <button
                            onClick={() => setViewMode('organic')}
                            className={`px-6 py-2 rounded-md text-sm font-bold transition-all ${viewMode === 'organic' ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/20' : 'text-gray-500 hover:text-gray-300'}`}
                        >
                            Fusión Orgánica
                        </button>
                    </div>

                    {viewMode === 'draft' && maxPages > 1 && (
                        <div className="flex items-center gap-4 bg-gray-900 px-4 py-2 rounded-xl border border-gray-800 shadow-lg">
                            <button
                                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                                disabled={currentPage === 1}
                                className="text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
                            >
                                <ChevronLeft size={20} />
                            </button>
                            <span className="text-xs font-black text-purple-400 uppercase tracking-tighter">Página {currentPage} de {maxPages}</span>
                            <button
                                onClick={() => setCurrentPage(Math.min(maxPages, currentPage + 1))}
                                disabled={currentPage === maxPages}
                                className="text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
                            >
                                <ChevronRight size={20} />
                            </button>
                        </div>
                    )}
                </div>

                {viewMode === 'draft' ? (
                    panels.length > 0 ? (
                        <EditorCanvas
                            panels={panels}
                            onSelectPanel={setSelectedPanel}
                            selectedId={selectedPanel?.id}
                            onUpdateLayout={handleUpdateLayout}
                            currentPage={currentPage}
                            dimensions={getCanvasDimensions()}
                            onDeletePanel={handleDeletePanel}
                        />
                    ) : (
                        <div className="flex flex-col items-center justify-center p-20 bg-gray-900/50 rounded-3xl border-2 border-dashed border-gray-800 w-full max-w-2xl min-h-[600px] animate-in fade-in zoom-in duration-500">
                            <div className="w-16 h-16 bg-purple-600/10 rounded-2xl flex items-center justify-center mb-6 border border-purple-500/20">
                                <LayoutGrid size={32} className="text-purple-500" />
                            </div>
                            <h3 className="text-xl font-black text-white uppercase tracking-tighter mb-2">Diseñando Layout...</h3>
                            <p className="text-gray-500 text-center max-w-sm text-sm leading-relaxed">
                                El Agente está organizando las escenas en las páginas especificadas según tu guion.
                            </p>
                            <div className="mt-8 flex gap-2">
                                <div className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                                <div className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                                <div className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce"></div>
                            </div>
                        </div>
                    )
                ) : (
                    <div className="flex flex-col gap-8 items-center w-full max-w-4xl">
                        {pages.map(page => (
                            <div key={page.page_number} className="w-full bg-gray-900 rounded-2xl p-4 border border-gray-800 shadow-2xl">
                                <h3 className="text-xs font-black text-gray-500 uppercase mb-4 px-2 tracking-tighter">Página {page.page_number} - Arte Fusionado</h3>
                                {page.merged_image_url ? (
                                    <img src={page.merged_image_url} alt="Merged" className="w-full rounded-lg shadow-2xl" />
                                ) : (
                                    <div className="w-full aspect-[2/3] bg-gray-950 rounded-lg flex items-center justify-center border-2 border-dashed border-gray-800">
                                        <div className="text-center">
                                            <Loader2 className="animate-spin text-purple-500 mx-auto mb-2" />
                                            <p className="text-sm text-gray-600">Procesando render final...</p>
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
                            <span className="text-[10px] bg-gray-800 px-2 py-1 rounded-full text-gray-400 font-mono">
                                ID: {String(selectedPanel.id).slice(-4)}
                            </span>
                        </div>

                        <div className="space-y-6 flex-1 overflow-auto pr-1">
                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2 tracking-widest">Escena</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl p-3 text-sm text-gray-400 h-20 resize-none outline-none focus:border-purple-500 transition-all shadow-inner"
                                    value={editingDescription}
                                    onChange={(e) => setEditingDescription(e.target.value)}
                                />
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2 tracking-widest">Prompt Visual AI</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-purple-900/30 rounded-xl p-3 text-sm text-gray-200 h-24 resize-none outline-none focus:border-purple-500 transition-all shadow-inner"
                                    value={editingPrompt}
                                    onChange={(e) => setEditingPrompt(e.target.value)}
                                />
                            </div>

                            <button className="w-full flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-xs font-bold py-3 rounded-xl transition border border-gray-700">
                                <RefreshCw size={14} />
                                Regenerar Imagen
                            </button>
                        </div>
                        <div className="mt-6 pt-6 border-t border-gray-800">
                            <button className="w-full py-3 bg-white text-black font-extrabold rounded-xl text-sm hover:bg-gray-200 transition active:scale-95">
                                Aplicar Cambios al Arte
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center p-10 text-center opacity-40">
                        <div className="w-16 h-16 bg-gray-800/50 rounded-3xl flex items-center justify-center mb-6 border border-gray-800 rotate-12">
                            <ImageIcon size={24} className="text-gray-600" />
                        </div>
                        <h3 className="text-gray-400 font-bold uppercase tracking-tighter">Sin selección</h3>
                        <p className="text-xs text-gray-600 mt-2 leading-relaxed font-medium">
                            Toca un panel en el lienzo para ajustar los detalles de la IA.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
