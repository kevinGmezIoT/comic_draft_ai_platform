import React, { useState, useEffect, useRef } from 'react';
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

    // Configuración Propuesta (la que se edita en la barra lateral)
    const [maxPages, setMaxPages] = useState(3);
    const [maxPanels, setMaxPanels] = useState(6);
    const [maxPanelsPerPage, setMaxPanelsPerPage] = useState(4);
    const [layoutStyle, setLayoutStyle] = useState('dynamic');

    // Configuración Activa (la que el backend dice que tiene el proyecto actualmente)
    const [activeMaxPages, setActiveMaxPages] = useState(3);

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
    const [editingStyle, setEditingStyle] = useState("");
    const [editingInstructions, setEditingInstructions] = useState("");
    const [useCurrentAsBase, setUseCurrentAsBase] = useState(false);
    const [editingBalloons, setEditingBalloons] = useState([]);
    const [mergeInstructions, setMergeInstructions] = useState("");
    const [saving, setSaving] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const isUpdatingLayout = React.useRef(false);
    const isGeneratingRef = React.useRef(false);
    const pollingInterval = React.useRef(null);
    const [pollingRetryCount, setPollingRetryCount] = useState(0);
    const panelsRef = useRef(panels);
    React.useEffect(() => { panelsRef.current = panels; }, [panels]);

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

                // Priorizar estados oficiales del backend para la visualización activa
                const backendMaxPages = response.data.max_pages || response.data.pages.length || 3;
                const backendMaxPanels = response.data.max_panels || allPanels.length || 6;
                const actualMaxPanelsPerPage = response.data.pages.reduce((max, p) => Math.max(max, p.panels.length), 0) || 4;

                const isBackendBusy = response.data.status === 'processing' || response.data.status === 'queued' || response.data.status === 'generating';

                // Solo actualizamos la estructura del proyecto si:
                // 1. No estamos en medio de una generación local (según el Ref)
                // 2. El backend NO está ocupado, O si está 'completed'
                if (!isGeneratingRef.current && !isBackendBusy) {
                    setActiveMaxPages(backendMaxPages);
                    setMaxPages(backendMaxPages);
                    setMaxPanels(backendMaxPanels);
                    setMaxPanelsPerPage(actualMaxPanelsPerPage);
                    setLayoutStyle(response.data.layout_style || 'dynamic');
                }
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

    // Ref to track whether we are initializing editingBalloons from panel selection
    const balloonSyncInit = useRef(false);
    const previousPanelRef = useRef(null);

    useEffect(() => {
        if (selectedPanel) {
            // Auto-save the PREVIOUS panel's balloons to the backend before switching
            const prevPanel = previousPanelRef.current;
            if (prevPanel && prevPanel.id !== selectedPanel.id) {
                const prevPanelData = panels.find(p => p.id === prevPanel.id);
                if (prevPanelData) {
                    axios.patch(`${import.meta.env.VITE_API_URL}/panels/${prevPanel.id}/update/`, {
                        balloons: prevPanelData.balloons || []
                    }).catch(e => console.error("Auto-save previous panel balloons failed:", e));
                }
            }
            previousPanelRef.current = selectedPanel;

            balloonSyncInit.current = true; // Flag to avoid writing back during init
            setEditingPrompt(selectedPanel.prompt || "");
            setEditingDescription(selectedPanel.scene_description || "");
            setEditingStyle(selectedPanel.panel_style || "");
            setEditingInstructions("");
            setUseCurrentAsBase(false);
            setEditingBalloons(selectedPanel.balloons || []);
            // Reset flag after the state update cycle
            setTimeout(() => { balloonSyncInit.current = false; }, 0);
        }
    }, [selectedPanel?.id]);

    // Live-sync editingBalloons changes back to the panels state for real-time canvas updates
    useEffect(() => {
        if (!selectedPanel || balloonSyncInit.current) return;
        setPanels(prev => prev.map(p =>
            p.id === selectedPanel.id ? { ...p, balloons: editingBalloons } : p
        ));
    }, [editingBalloons]);

    const handleGenerate = async (settings = {}) => {
        setLoading(true);
        isGeneratingRef.current = true;
        setError(null);

        // Use the ref to guarantee we have the absolute latest panels state,
        // not a potentially stale closure capture.
        const latestPanels = panelsRef.current;

        // Map existing panels for the agent payload
        const existingPanels = latestPanels.map(p => ({
            id: p.id,
            page_number: p.page_number,
            order_in_page: p.order,
            layout: p.layout,
            prompt: p.prompt,
            scene_description: p.scene_description,
            balloons: p.balloons || []
        }));

        // Persist all current panel states to avoid data loss from polling
        // (especially important for balloon positions)
        try {
            await Promise.all(latestPanels.map(p =>
                axios.patch(`${import.meta.env.VITE_API_URL}/panels/${p.id}/update/`, {
                    balloons: p.balloons || [],
                    layout: p.layout
                })
            ));
        } catch (e) { console.error("Sync before generate failed:", e); }

        // Siempre intentamos sincronizar los paneles existentes si los hay, 
        // para que el agente reconozca IDs de paneles ya creados y mantenga sus layouts.
        const panelsToSync = (panels.length > 0) ? existingPanels : [];

        const currentMaxPages = settings.max_pages || maxPages;
        const requestedPanels = settings.panels_per_page || maxPanelsPerPage;

        if (settings.max_pages) setMaxPages(settings.max_pages);
        if (settings.panels_per_page) setMaxPanelsPerPage(settings.panels_per_page);
        if (settings.layout_style) setLayoutStyle(settings.layout_style);

        // Actualizamos el indicador de páginas activas para dar feedback inmediato.
        // Si es una regeneración total, es obligatorio. Si es parcial (una página),
        // también lo hacemos para que el indicador de navegación refleje la nueva estructura.
        setActiveMaxPages(currentMaxPages);

        // Si la página actual queda fuera del nuevo rango (ej: redujiste de 5 a 3 páginas),
        // volvemos a la página 1 para evitar errores visuales.
        if (currentPage > currentMaxPages) {
            setCurrentPage(1);
        }

        // Si estamos regenerando una página específica, el max_panels del payload 
        // debería representar el total esperado tras el cambio, o simplemente le pasamos

        // El "techo" del proyecto: el mayor entre lo pedido y lo que ya existe en otras páginas
        const actualPanelsInOtherPages = pages
            .filter(p => p.page_number !== settings.page_number)
            .reduce((max, p) => Math.max(max, p.panels.length), 0);
        const projectDensity = Math.max(requestedPanels, actualPanelsInOtherPages);

        // Si es regeneración de página individual, usamos lo que ya tiene el proyecto para el resto
        // Si es regeneración total, usamos lo propuesto
        const currentMaxPanels = settings.page_number
            ? (panels.filter(p => p.page_number !== settings.page_number).length + requestedPanels)
            : (currentMaxPages * requestedPanels);

        console.log("DEBUG: [FRONTEND] Settings State - Project Density:", projectDensity, "Target Panels for this Page:", requestedPanels, "Total Max Panels:", currentMaxPanels);

        const config = {
            max_pages: currentMaxPages,
            max_panels: currentMaxPanels,
            panels_per_page: requestedPanels,
            layout_style: settings.layout_style || layoutStyle,
            plan_only: settings.plan_only || false,
            page_number: settings.page_number,
            panels: panelsToSync
        };

        console.log("DEBUG: [FRONTEND] Generating with Config:", config);

        try {
            // Switch to editor immediately
            setView('editor');
            if (settings.plan_only) setViewMode('draft');

            if (settings.skip_agent) {
                // No need to call generate, just ensure we have data
                setLoading(false);
                return;
            }

            let response;
            if (settings.action === 'regenerate_panel') {
                response = await axios.post(`${import.meta.env.VITE_API_URL}/panels/${settings.panel_id}/regenerate/`, {
                    prompt: settings.prompt,
                    scene_description: settings.scene_description,
                    balloons: settings.balloons,
                    panel_style: settings.panel_style,
                    instructions: settings.instructions,
                    use_current_as_base: settings.use_current_as_base
                });
            } else {
                response = await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/generate/`, config);
            }

            // If the response is already completed (Sync Path), fetch data immediately
            if (response.data && response.data.status === 'completed') {
                await fetchProjectData();
                setLoading(false);
                isGeneratingRef.current = false;
                return;
            }

            startPollingStatus();
        } catch (error) {
            console.error("Error generating comic:", error);
            setError("Error al iniciar la generación.");
            setLoading(false);
            isGeneratingRef.current = false;
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

    const handleBalloonChange = (panelId, balloonIdx, updatedBalloon) => {
        isUpdatingLayout.current = true;
        setPanels(prev => prev.map(p => {
            if (p.id !== panelId) return p;
            const newBalloons = [...(p.balloons || [])];
            newBalloons[balloonIdx] = updatedBalloon;
            return { ...p, balloons: newBalloons };
        }));
        // Also update editingBalloons if this panel is selected
        if (selectedPanel?.id === panelId) {
            setEditingBalloons(prev => {
                const nb = [...prev];
                nb[balloonIdx] = updatedBalloon;
                return nb;
            });
        }
        // Release polling lock after 1.5s to let backend stabilize
        setTimeout(() => { isUpdatingLayout.current = false; }, 1500);
    };

    const handleDeleteBalloon = (panelId, balloonIdx) => {
        setPanels(prev => prev.map(p => {
            if (p.id !== panelId) return p;
            const newBalloons = (p.balloons || []).filter((_, i) => i !== balloonIdx);
            return { ...p, balloons: newBalloons };
        }));
        if (selectedPanel?.id === panelId) {
            setEditingBalloons(prev => prev.filter((_, i) => i !== balloonIdx));
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
                    isGeneratingRef.current = false;
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
                        isGeneratingRef.current = false;
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
                                value={isNaN(maxPages) ? "" : maxPages}
                                onChange={(e) => {
                                    const val = e.target.value;
                                    if (val === "") {
                                        setMaxPages(NaN);
                                    } else {
                                        const n = parseInt(val);
                                        if (!isNaN(n)) setMaxPages(n);
                                    }
                                }}
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
                        onClick={() => handleGenerate({
                            plan_only: true,
                            page_number: currentPage,
                            max_pages: maxPages,
                            panels_per_page: maxPanelsPerPage
                        })}
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

                    {viewMode === 'draft' && activeMaxPages > 1 && (
                        <div className="flex items-center gap-4 bg-gray-900 px-4 py-2 rounded-xl border border-gray-800 shadow-lg">
                            <button
                                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                                disabled={currentPage === 1}
                                className="text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
                            >
                                <ChevronLeft size={20} />
                            </button>
                            <span className="text-xs font-black text-purple-400 uppercase tracking-tighter">Página {currentPage} de {activeMaxPages}</span>
                            <button
                                onClick={() => setCurrentPage(Math.min(activeMaxPages, currentPage + 1))}
                                disabled={currentPage === activeMaxPages}
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
                            onBalloonChange={handleBalloonChange}
                            onDeleteBalloon={handleDeleteBalloon}
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
                        {/* Panel de Acciones Globales */}
                        <div className="w-full flex flex-col md:flex-row gap-4 mb-2">
                            <div className="flex-1 bg-gray-900 rounded-2xl p-6 border border-purple-500/30 shadow-2xl space-y-4">
                                <h3 className="text-sm font-black text-purple-400 uppercase tracking-tighter flex items-center gap-2">
                                    <Wand2 size={16} />
                                    Fusión Global (Todas las páginas)
                                </h3>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl p-4 text-sm text-gray-300 h-20 resize-none outline-none focus:border-purple-500 transition-all shadow-inner"
                                    placeholder="Instrucciones para TODAS las páginas (ej: estilo acuarela)..."
                                    value={mergeInstructions}
                                    onChange={(e) => setMergeInstructions(e.target.value)}
                                />
                                <div className="flex gap-3">
                                    <button
                                        onClick={async () => {
                                            setRegenerating(true);
                                            try {
                                                await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/regenerate-merge/`, {
                                                    instructions: mergeInstructions
                                                });
                                                startPollingStatus();
                                            } catch (e) {
                                                console.error(e);
                                                setRegenerating(false);
                                            }
                                        }}
                                        disabled={regenerating}
                                        className="flex-1 flex items-center justify-center gap-3 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-800 text-white font-black py-3 rounded-xl transition-all shadow-lg active:scale-95"
                                    >
                                        {regenerating ? <Loader2 className="animate-spin" /> : <RefreshCw size={18} />}
                                        {regenerating ? "Procesando..." : "Regenerar Todo con Prompt"}
                                    </button>
                                    <button
                                        onClick={async () => {
                                            setRegenerating(true);
                                            try {
                                                await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/regenerate-merge/`, {
                                                    instructions: "" // Sincronización pura
                                                });
                                                startPollingStatus();
                                            } catch (e) {
                                                console.error(e);
                                                setRegenerating(false);
                                            }
                                        }}
                                        disabled={regenerating}
                                        className="flex-1 flex items-center justify-center gap-3 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-900 text-gray-300 font-bold py-3 rounded-xl transition-all border border-gray-700 active:scale-95"
                                    >
                                        <Zap size={18} className="text-yellow-500" />
                                        Sincronizar desde Storyline
                                    </button>
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full">
                            {pages.map(page => (
                                <div key={page.page_number} className="flex flex-col gap-4 bg-gray-900 rounded-3xl p-5 border border-gray-800 shadow-2xl hover:border-purple-500/20 transition-all group">
                                    <div className="flex justify-between items-center px-1">
                                        <h3 className="text-xs font-black text-gray-500 uppercase tracking-tighter group-hover:text-purple-400 transition-colors">Página {page.page_number} - Arte Fusionado</h3>
                                        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => {
                                                    const link = document.createElement('a');
                                                    link.href = page.merged_image_url;
                                                    link.download = `page_${page.page_number}.png`;
                                                    link.click();
                                                }}
                                                className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-500 hover:text-white transition-colors"
                                                title="Descargar"
                                            >
                                                <Download size={14} />
                                            </button>
                                        </div>
                                    </div>

                                    <div className="relative bg-gray-950 rounded-2xl overflow-hidden border border-gray-800 shadow-inner group/img">
                                        {page.merged_image_url ? (
                                            <img src={page.merged_image_url} alt="Merged" className="w-full h-auto block transition-transform duration-500 group-hover/img:scale-105" />
                                        ) : (
                                            <div className="w-full aspect-[2/3] flex flex-col items-center justify-center">
                                                <Loader2 className="animate-spin text-purple-500 mb-2" />
                                                <p className="text-[10px] text-gray-600 font-bold uppercase">Procesando render...</p>
                                            </div>
                                        )}

                                        {/* Overlay para regeneración rápida por página */}
                                        <div className="absolute inset-0 bg-gray-950/80 opacity-0 group-hover/img:opacity-100 transition-all duration-300 flex flex-col items-center justify-center p-6 text-center backdrop-blur-sm">
                                            <p className="text-[10px] font-black text-purple-400 uppercase mb-4 tracking-widest">Ajuste Individual</p>
                                            <textarea
                                                className="w-full bg-gray-900 border border-gray-700 rounded-xl p-3 text-xs text-white h-24 mb-4 resize-none outline-none focus:border-purple-500"
                                                placeholder="Instrucciones solo para esta página..."
                                                onClick={(e) => e.stopPropagation()}
                                                id={`instr-page-${page.page_number}`}
                                            />
                                            <button
                                                onClick={async (e) => {
                                                    e.stopPropagation();
                                                    const instr = document.getElementById(`instr-page-${page.page_number}`).value;
                                                    setRegenerating(true);
                                                    try {
                                                        await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/regenerate-merge/`, {
                                                            instructions: instr,
                                                            page_number: page.page_number
                                                        });
                                                        startPollingStatus();
                                                    } catch (err) {
                                                        console.error(err);
                                                        setRegenerating(false);
                                                    }
                                                }}
                                                disabled={regenerating}
                                                className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-2 rounded-lg text-xs transition-colors shadow-lg active:scale-95"
                                            >
                                                {regenerating ? "Regenerando..." : `Regenerar Página ${page.page_number}`}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
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
                                <div className="flex justify-between items-center mb-3">
                                    <label className="text-xs font-bold text-gray-500 uppercase tracking-widest">Globos de Diálogo</label>
                                    <button
                                        onClick={() => {
                                            setEditingBalloons(prev => [...prev, {
                                                text: "Nuevo texto",
                                                type: "dialogue",
                                                character: "",
                                                position_hint: "top-left",
                                                fontSize: 13,
                                                width: 180,
                                                height: 70
                                            }]);
                                        }}
                                        className="text-[10px] font-bold text-purple-400 hover:text-purple-300 bg-purple-500/10 hover:bg-purple-500/20 px-2 py-1 rounded-lg transition"
                                    >
                                        + Agregar
                                    </button>
                                </div>
                                <div className="space-y-3 max-h-64 overflow-auto pr-2">
                                    {editingBalloons.map((balloon, idx) => (
                                        <div key={idx} className="bg-gray-950 border border-gray-800 rounded-xl p-3 space-y-2">
                                            <div className="flex justify-between items-center">
                                                <input
                                                    className="text-[10px] font-bold text-purple-400 uppercase bg-transparent outline-none w-20"
                                                    value={balloon.character || ""}
                                                    placeholder="Personaje"
                                                    onChange={(e) => {
                                                        const nb = [...editingBalloons];
                                                        nb[idx] = { ...nb[idx], character: e.target.value };
                                                        setEditingBalloons(nb);
                                                    }}
                                                />
                                                <div className="flex items-center gap-1">
                                                    <select
                                                        className="text-[9px] text-gray-400 bg-gray-900 px-1.5 py-0.5 rounded outline-none border border-gray-800"
                                                        value={balloon.type}
                                                        onChange={(e) => {
                                                            const nb = [...editingBalloons];
                                                            nb[idx] = { ...nb[idx], type: e.target.value };
                                                            setEditingBalloons(nb);
                                                        }}
                                                    >
                                                        <option value="dialogue">Diálogo</option>
                                                        <option value="narration">Narración</option>
                                                        <option value="thought">Pensamiento</option>
                                                    </select>
                                                    <button
                                                        onClick={() => setEditingBalloons(prev => prev.filter((_, i) => i !== idx))}
                                                        className="text-red-500 hover:text-red-400 p-0.5 hover:bg-red-500/10 rounded transition"
                                                        title="Eliminar globo"
                                                    >
                                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                                                    </button>
                                                </div>
                                            </div>
                                            <textarea
                                                className="w-full bg-transparent text-xs text-gray-300 outline-none resize-none h-12"
                                                value={balloon.text}
                                                onChange={(e) => {
                                                    const nb = [...editingBalloons];
                                                    nb[idx] = { ...nb[idx], text: e.target.value };
                                                    setEditingBalloons(nb);
                                                }}
                                            />
                                            <div className="flex items-center gap-2">
                                                <span className="text-[9px] text-gray-600 shrink-0">Tamaño:</span>
                                                <input
                                                    type="range"
                                                    min="8" max="32" step="1"
                                                    value={balloon.fontSize || 13}
                                                    onChange={(e) => {
                                                        const nb = [...editingBalloons];
                                                        nb[idx] = { ...nb[idx], fontSize: parseInt(e.target.value) };
                                                        setEditingBalloons(nb);
                                                    }}
                                                    className="flex-1 h-1 accent-purple-500"
                                                />
                                                <span className="text-[9px] text-gray-500 w-6 text-right">{balloon.fontSize || 13}</span>
                                            </div>
                                        </div>
                                    ))}
                                    {editingBalloons.length === 0 && (
                                        <p className="text-[10px] text-gray-600 italic text-center py-2">No hay globos en este panel.</p>
                                    )}
                                </div>
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2 tracking-widest">Estilo del Panel (Personalizado)</label>
                                <input
                                    type="text"
                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl p-3 text-sm text-gray-400 outline-none focus:border-purple-500 transition-all shadow-inner"
                                    placeholder="Ej: Comic Noir, 90s Manga..."
                                    value={editingStyle}
                                    onChange={(e) => setEditingStyle(e.target.value)}
                                />
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2 tracking-widest">Instrucciones de Regeneración</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl p-3 text-sm text-gray-400 h-20 resize-none outline-none focus:border-purple-500 transition-all shadow-inner"
                                    placeholder="Ej: Haz que llueva, cambia la ropa a rojo..."
                                    value={editingInstructions}
                                    onChange={(e) => setEditingInstructions(e.target.value)}
                                />
                                <div className="flex items-center gap-2 mt-2">
                                    <input
                                        type="checkbox"
                                        id="useBase"
                                        checked={useCurrentAsBase}
                                        onChange={(e) => setUseCurrentAsBase(e.target.checked)}
                                        className="accent-purple-600"
                                    />
                                    <label htmlFor="useBase" className="text-[10px] text-gray-500 font-bold uppercase cursor-pointer">Usar imagen actual como base (I2I)</label>
                                </div>
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase block mb-2 tracking-widest">Imagen de Referencia</label>
                                <div className="flex flex-col gap-2">
                                    <input
                                        type="file"
                                        className="hidden"
                                        id="refImageUpload"
                                        onChange={async (e) => {
                                            const file = e.target.files[0];
                                            if (file) {
                                                setLoading(true);
                                                const formData = new FormData();
                                                formData.append('image', file);
                                                try {
                                                    await axios.post(`${import.meta.env.VITE_API_URL}/panels/${selectedPanel.id}/upload-reference/`, formData, {
                                                        headers: { 'Content-Type': 'multipart/form-data' }
                                                    });
                                                    await fetchProjectData();
                                                    // Actualizar el panel seleccionado localmente para reflejar el cambio inmediato
                                                    setSelectedPanel(prev => ({ ...prev, reference_image: true }));
                                                } catch (err) {
                                                    console.error("Error uploading reference image:", err);
                                                    setError("Error al subir la imagen de referencia.");
                                                } finally {
                                                    setLoading(false);
                                                }
                                            }
                                        }}
                                    />
                                    <button
                                        onClick={() => document.getElementById('refImageUpload').click()}
                                        className="w-full py-2 bg-gray-800 hover:bg-gray-700 border border-dashed border-gray-600 rounded-lg text-[10px] font-bold text-gray-400 transition"
                                    >
                                        {selectedPanel.reference_image ? "Cambiar Referencia" : "+ Subir Referencia"}
                                    </button>
                                </div>
                            </div>

                            <button
                                onClick={async () => {
                                    // Auto-save balloon and text changes before regenerating
                                    try {
                                        await axios.patch(`${import.meta.env.VITE_API_URL}/panels/${selectedPanel.id}/update/`, {
                                            prompt: editingPrompt,
                                            scene_description: editingDescription,
                                            balloons: editingBalloons
                                        });
                                    } catch (e) { console.error("Auto-save before regenerate failed:", e); }
                                    handleGenerate({
                                        action: 'regenerate_panel',
                                        panel_id: selectedPanel.id,
                                        prompt: editingPrompt,
                                        scene_description: editingDescription,
                                        balloons: editingBalloons,
                                        panel_style: editingStyle,
                                        instructions: editingInstructions,
                                        use_current_as_base: useCurrentAsBase,
                                        skip_agent: false
                                    });
                                }}
                                className="w-full flex items-center justify-center gap-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 text-xs font-bold py-3 rounded-xl transition border border-purple-500/30"
                            >
                                <RefreshCw size={14} />
                                Regenerar Imagen con Contexto
                            </button>
                        </div>
                        <div className="mt-6 pt-6 border-t border-gray-800">
                            <button
                                onClick={async () => {
                                    setSaving(true);
                                    try {
                                        await axios.patch(`${import.meta.env.VITE_API_URL}/panels/${selectedPanel.id}/update/`, {
                                            prompt: editingPrompt,
                                            scene_description: editingDescription,
                                            balloons: editingBalloons
                                        });
                                        await fetchProjectData();
                                        alert("Cambios guardados localmente. Regenera el 'Arte Final' para verlos mezclados.");
                                    } catch (e) { console.error(e); } finally { setSaving(false); }
                                }}
                                disabled={saving}
                                className="w-full py-3 bg-white text-black font-extrabold rounded-xl text-sm hover:bg-gray-200 transition active:scale-95 disabled:opacity-50"
                            >
                                {saving ? "Guardando..." : "Aplicar Cambios al Arte"}
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
