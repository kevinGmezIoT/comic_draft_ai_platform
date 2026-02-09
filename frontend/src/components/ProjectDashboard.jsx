import React, { useState, useEffect } from 'react';
import {
    Users, Map, FileText, Zap,
    ArrowRight, Edit3, Trash2, Plus, Layout,
    Save, X, BookOpen, Palette, Info, Upload, Loader2
} from 'lucide-react';
import axios from 'axios';

const ProjectDashboard = ({ projectId, onStartGeneration }) => {
    const [project, setProject] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isEditingGlobal, setIsEditingGlobal] = useState(false);
    const [globalData, setGlobalData] = useState({ world_bible: '', style_guide: '' });
    const [isLayoutModalOpen, setIsLayoutModalOpen] = useState(false);
    const [layoutSettings, setLayoutSettings] = useState({
        max_pages: 3,
        max_panels: 6,
        panels_per_page: 6,
        layout_style: 'dynamic'
    });

    // Synchronize layout settings with project data when available
    useEffect(() => {
        if (project) {
            const allPanels = project.pages?.flatMap(p => p.panels) || [];
            const actualMaxPanelsPerPage = project.pages?.reduce((max, p) => Math.max(max, p.panels.length), 0) || 4;

            setLayoutSettings({
                max_pages: project.max_pages || project.pages?.length || 3,
                max_panels: project.max_panels || allPanels.length || 6,
                panels_per_page: actualMaxPanelsPerPage,
                layout_style: project.layout_style || 'dynamic'
            });
        }
    }, [project]);

    // Modal state
    const [modal, setModal] = useState({ open: false, type: '', data: null }); // type: 'char' | 'scene' | 'note'

    const fetchProject = async () => {
        if (!projectId) return;
        try {
            const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);
            setProject(response.data);
            setGlobalData({
                world_bible: response.data.world_bible || '',
                style_guide: response.data.style_guide || ''
            });
            setLoading(false);
        } catch (error) {
            console.error("Error fetching project:", error);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProject();
    }, [projectId]);

    const handleSaveGlobal = async () => {
        try {
            await axios.patch(`${import.meta.env.VITE_API_URL}/projects/${projectId}/update/`, globalData);
            setProject({ ...project, ...globalData });
            setIsEditingGlobal(false);
        } catch (error) {
            console.error("Error saving global context:", error);
        }
    };

    const handleDelete = async (type, id) => {
        if (!window.confirm("¿Estás seguro de eliminar este elemento?")) return;
        try {
            let url = '';
            if (type === 'char') url = `${import.meta.env.VITE_API_URL}/projects/characters/${id}/`;
            if (type === 'scene') url = `${import.meta.env.VITE_API_URL}/projects/sceneries/${id}/`;
            if (type === 'note') url = `${import.meta.env.VITE_API_URL}/projects/notes/${id}/`;

            await axios.delete(url);
            fetchProject();
        } catch (error) {
            console.error("Error deleting item:", error);
        }
    };

    const handleModalSubmit = async (formData) => {
        try {
            let url = '';
            const isEdit = !!modal.data?.id;

            if (modal.type === 'char') {
                url = isEdit
                    ? `${import.meta.env.VITE_API_URL}/projects/characters/${modal.data.id}/`
                    : `${import.meta.env.VITE_API_URL}/projects/${projectId}/characters/create/`;
            } else if (modal.type === 'scene') {
                url = isEdit
                    ? `${import.meta.env.VITE_API_URL}/projects/sceneries/${modal.data.id}/`
                    : `${import.meta.env.VITE_API_URL}/projects/${projectId}/sceneries/create/`;
            } else if (modal.type === 'note') {
                url = isEdit
                    ? `${import.meta.env.VITE_API_URL}/projects/notes/${modal.data.id}/`
                    : `${import.meta.env.VITE_API_URL}/projects/${projectId}/notes/`;
            }

            if (isEdit) {
                await axios.patch(url, formData);
            } else {
                await axios.post(url, formData);
            }

            setModal({ open: false, type: '', data: null });
            fetchProject();
        } catch (error) {
            console.error("Error submitting modal:", error);
        }
    };

    if (loading) return (
        <div className="flex flex-col items-center justify-center h-[60vh] text-gray-400">
            <Loader2 className="animate-spin mb-4 text-purple-500" size={40} />
            <p className="text-xl font-bold">Invocando el Mundo...</p>
        </div>
    );

    if (!project) return <div>Error al cargar el proyecto</div>;

    return (
        <div className="w-full max-w-6xl space-y-12 animate-in fade-in duration-500 pb-20 px-4">
            {/* Project Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b border-gray-800 pb-8">
                <div>
                    <div className="flex items-center gap-3 mb-2">
                        <span className="bg-purple-600/20 text-purple-400 text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border border-purple-500/30">
                            Proyecto Activo
                        </span>
                    </div>
                    <h1 className="text-5xl font-black text-white tracking-tight">{project.name}</h1>
                    <p className="text-gray-400 mt-3 text-lg max-w-2xl leading-relaxed">{project.description || "Sin descripción proporcionada."}</p>
                </div>
                <button
                    onClick={() => setIsLayoutModalOpen(true)}
                    className="group bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-10 py-5 rounded-2xl font-black flex items-center gap-4 transition-all shadow-2xl shadow-purple-500/40 hover:scale-[1.02] active:scale-95 whitespace-nowrap"
                >
                    <Layout size={24} />
                    GENERAR CÓMIC
                    <ArrowRight size={24} className="group-hover:translate-x-1 transition-transform" />
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* World Bible Section */}
                <div className="lg:col-span-2 space-y-8">
                    <section className="bg-gray-900/40 border border-gray-800 rounded-[2.5rem] p-10 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-purple-600/5 blur-[100px] rounded-full -mr-32 -mt-32"></div>

                        <div className="flex items-center justify-between mb-8 relative z-10">
                            <div>
                                <h3 className="text-xl font-black text-white flex items-center gap-3">
                                    <BookOpen size={24} className="text-purple-400" />
                                    Biblia del Mundo
                                </h3>
                                <p className="text-xs text-gray-500 mt-1 uppercase tracking-widest font-bold">Contexto Global Inmutable</p>
                            </div>
                            <button
                                onClick={() => setIsEditingGlobal(!isEditingGlobal)}
                                className={`p-3 rounded-xl transition-all ${isEditingGlobal ? 'bg-green-600 text-white shadow-lg shadow-green-500/20' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                            >
                                {isEditingGlobal ? <Save size={20} /> : <Edit3 size={20} />}
                            </button>
                        </div>

                        {isEditingGlobal ? (
                            <div className="space-y-6 relative z-10 animate-in fade-in slide-in-from-top-4">
                                <div>
                                    <label className="block text-[10px] font-bold text-gray-500 mb-2 uppercase tracking-widest">Información Global</label>
                                    <textarea
                                        className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-4 text-white focus:border-purple-500 outline-none h-32 text-sm font-mono"
                                        value={globalData.world_bible}
                                        onChange={e => setGlobalData({ ...globalData, world_bible: e.target.value })}
                                        placeholder="Nombres, relaciones, amigos, localización general..."
                                    />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-bold text-gray-500 mb-2 uppercase tracking-widest">Estilo Visual</label>
                                    <textarea
                                        className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-4 text-white focus:border-purple-500 outline-none h-24 text-sm font-mono"
                                        value={globalData.style_guide}
                                        onChange={e => setGlobalData({ ...globalData, style_guide: e.target.value })}
                                        placeholder="Estética, paleta de colores, trazos..."
                                    />
                                </div>
                                <div className="flex justify-end gap-3">
                                    <button onClick={() => setIsEditingGlobal(false)} className="px-6 py-2 text-gray-500 font-bold hover:text-white">Cancelar</button>
                                    <button onClick={handleSaveGlobal} className="bg-purple-600 text-white px-8 py-2 rounded-xl font-bold shadow-lg shadow-purple-500/20 hover:bg-purple-500 transition-all">Guardar Cambios</button>
                                </div>
                            </div>
                        ) : (
                            <div className="grid md:grid-cols-2 gap-8 relative z-10">
                                <div className="space-y-4">
                                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Lore del Mundo</h4>
                                    <div className="bg-gray-950/50 rounded-2xl p-6 border border-gray-800/50 min-h-[140px] text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">
                                        {project.world_bible || <span className="text-gray-700 italic">No hay información global definida.</span>}
                                    </div>
                                </div>
                                <div className="space-y-4">
                                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Identidad Visual</h4>
                                    <div className="bg-gray-950/50 rounded-2xl p-6 border border-gray-800/50 min-h-[140px] text-gray-300 text-sm leading-relaxed flex items-start gap-3">
                                        <Palette size={18} className="text-purple-400 shrink-0 mt-1" />
                                        <p>{project.style_guide || <span className="text-gray-700 italic">No hay guía de estilo.</span>}</p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </section>

                    {/* Characters List */}
                    <div className="bg-gray-900/40 border border-gray-800 rounded-[2.5rem] p-10">
                        <div className="flex items-center justify-between mb-8">
                            <h3 className="text-xl font-black text-white flex items-center gap-3">
                                <Users size={24} className="text-blue-400" />
                                Personajes
                            </h3>
                            <button
                                onClick={() => setModal({ open: true, type: 'char', data: null })}
                                className="bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl transition-all shadow-lg shadow-blue-500/20"
                            >
                                <Plus size={20} />
                            </button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {project.characters?.map((char) => (
                                <div key={char.id} className="bg-gray-950 p-6 rounded-3xl border border-gray-800 hover:border-blue-500/30 transition-all group">
                                    <div className="flex justify-between items-start mb-4">
                                        <h4 className="font-black text-white text-xl">{char.name}</h4>
                                        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button onClick={() => setModal({ open: true, type: 'char', data: char })} className="text-gray-500 hover:text-white p-2 bg-gray-900 rounded-lg"><Edit3 size={14} /></button>
                                            <button onClick={() => handleDelete('char', char.id)} className="text-gray-500 hover:text-red-400 p-2 bg-gray-900 rounded-lg"><Trash2 size={14} /></button>
                                        </div>
                                    </div>
                                    <p className="text-sm text-gray-500 line-clamp-2 leading-relaxed">{char.description}</p>
                                    <div className="mt-4 flex items-center gap-2 text-xs text-blue-400/60 font-bold uppercase tracking-widest">
                                        {char.metadata?.file_name && (
                                            <span className="bg-blue-400/5 px-3 py-1 rounded-lg flex items-center gap-2 border border-blue-400/10">
                                                <FileText size={12} /> {char.metadata.file_name}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )) || <p className="text-gray-600 italic">No hay personajes registrados.</p>}
                        </div>
                    </div>

                    {/* Sceneries List */}
                    <div className="bg-gray-900/40 border border-gray-800 rounded-[2.5rem] p-10">
                        <div className="flex items-center justify-between mb-8">
                            <h3 className="text-xl font-black text-white flex items-center gap-3">
                                <Map size={24} className="text-green-400" />
                                Escenarios
                            </h3>
                            <button
                                onClick={() => setModal({ open: true, type: 'scene', data: null })}
                                className="bg-green-600 hover:bg-green-500 text-white p-3 rounded-xl transition-all shadow-lg shadow-green-500/20"
                            >
                                <Plus size={20} />
                            </button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {project.sceneries?.map((scene) => (
                                <div key={scene.id} className="bg-gray-950 p-6 rounded-3xl border border-gray-800 hover:border-green-500/30 transition-all group">
                                    <div className="flex justify-between items-start mb-4">
                                        <h4 className="font-black text-white text-xl">{scene.name}</h4>
                                        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button onClick={() => setModal({ open: true, type: 'scene', data: scene })} className="text-gray-500 hover:text-white p-2 bg-gray-900 rounded-lg"><Edit3 size={14} /></button>
                                            <button onClick={() => handleDelete('scene', scene.id)} className="text-gray-500 hover:text-red-400 p-2 bg-gray-900 rounded-lg"><Trash2 size={14} /></button>
                                        </div>
                                    </div>
                                    <p className="text-sm text-gray-500 line-clamp-2 leading-relaxed">{scene.description}</p>
                                </div>
                            )) || <p className="text-gray-600 italic">No hay escenarios registrados.</p>}
                        </div>
                    </div>
                </div>

                {/* Sidebar Info - Notes & Script */}
                <div className="space-y-8">
                    {/* Script Section */}
                    <div className="bg-gray-900/40 border border-gray-800 rounded-[2.5rem] p-8">
                        <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em] mb-6 flex items-center gap-3">
                            <FileText size={18} className="text-purple-400" />
                            Guión Maestro
                        </h3>
                        <div className="bg-gray-950 rounded-2xl p-8 border border-gray-800 text-center group cursor-pointer hover:border-purple-600/50 transition-all">
                            <div className="w-16 h-16 bg-gray-900 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                                <FileText size={32} className="text-gray-600 group-hover:text-purple-400" />
                            </div>
                            <p className="text-white font-bold mb-1">guion_principal.pdf</p>
                            <p className="text-[10px] text-gray-500 uppercase font-black">Reemplazar Archivo</p>
                        </div>
                    </div>

                    {/* Important Notes */}
                    <div className="bg-gray-900/40 border border-gray-800 rounded-[2.5rem] p-8">
                        <div className="flex items-center justify-between mb-6">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em] flex items-center gap-3">
                                <Info size={18} className="text-yellow-500" />
                                Cosas Importantes
                            </h3>
                            <button
                                onClick={() => setModal({ open: true, type: 'note', data: null })}
                                className="text-yellow-500 hover:bg-yellow-500/10 p-2 rounded-lg transition-all"
                            >
                                <Plus size={16} />
                            </button>
                        </div>
                        <div className="space-y-4">
                            {project.notes?.map(note => (
                                <div key={note.id} className="bg-gray-950/50 p-5 rounded-2xl border border-gray-800/50 hover:border-yellow-500/30 transition-all group">
                                    <div className="flex justify-between items-start mb-2">
                                        <h5 className="font-bold text-gray-200 text-sm">{note.title}</h5>
                                        <button onClick={() => handleDelete('note', note.id)} className="text-gray-600 hover:text-red-400 p-1 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 size={12} /></button>
                                    </div>
                                    <p className="text-[11px] text-gray-500 line-clamp-3">{note.content}</p>
                                    {note.file_url && (
                                        <div className="mt-3 text-[10px] text-yellow-500/60 font-bold flex items-center gap-2">
                                            <Upload size={10} /> Documento Adjunto
                                        </div>
                                    )}
                                </div>
                            )) || <p className="text-xs text-gray-600 italic text-center">Sin notas relevantes.</p>}
                        </div>
                    </div>
                </div>
            </div>

            {/* Global Modal Component */}
            {modal.open && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-6 animate-in fade-in duration-200">
                    <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => setModal({ open: false, type: '', data: null })}></div>
                    <div className="bg-gray-900 border border-gray-800 w-full max-w-lg rounded-3xl p-8 relative z-10 shadow-2xl animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-2xl font-black text-white uppercase tracking-tight">
                                {modal.data?.id ? 'Editar' : 'Añadir'} {modal.type === 'char' ? 'Personaje' : modal.type === 'scene' ? 'Escenario' : 'Nota'}
                            </h3>
                            <button onClick={() => setModal({ open: false, type: '', data: null })} className="text-gray-500 hover:text-white transition-colors">
                                <X size={24} />
                            </button>
                        </div>

                        <AssetForm
                            type={modal.type}
                            initialData={modal.data}
                            onSubmit={handleModalSubmit}
                            onCancel={() => setModal({ open: false, type: '', data: null })}
                        />
                    </div>
                </div>
            )}

            {/* Layout Settings Modal */}
            {isLayoutModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-6 animate-in fade-in duration-200">
                    <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => setIsLayoutModalOpen(false)}></div>
                    <div className="bg-gray-900 border border-gray-800 w-full max-w-lg rounded-3xl p-10 relative z-10 shadow-2xl animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-8">
                            <div>
                                <h3 className="text-3xl font-black text-white uppercase tracking-tight">Preferencias de Maquetación</h3>
                                <p className="text-gray-500 text-xs font-bold uppercase tracking-widest mt-1">Configura antes de generar</p>
                            </div>
                            <button onClick={() => setIsLayoutModalOpen(false)} className="text-gray-500 hover:text-white transition-colors">
                                <X size={24} />
                            </button>
                        </div>

                        <div className="space-y-8">
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 mb-3 uppercase tracking-widest">Máximo de Páginas</label>
                                <input
                                    type="number"
                                    min="1" max="10"
                                    className="w-full bg-gray-950 border border-gray-700 rounded-xl px-6 py-4 text-white focus:border-purple-500 outline-none transition-all"
                                    value={layoutSettings.max_pages}
                                    onChange={e => setLayoutSettings({ ...layoutSettings, max_pages: parseInt(e.target.value) })}
                                />
                            </div>

                            <div className="grid grid-cols-1 gap-4">
                                <div>
                                    <label className="block text-[10px] font-bold text-gray-500 mb-3 uppercase tracking-widest">Paneles por Página</label>
                                    <select
                                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-6 py-4 text-white focus:border-purple-500 outline-none appearance-none"
                                        value={layoutSettings.panels_per_page || 'auto'}
                                        onChange={e => setLayoutSettings({ ...layoutSettings, panels_per_page: e.target.value === 'auto' ? null : parseInt(e.target.value) })}
                                    >
                                        <option value="auto">Auto (IA Decide)</option>
                                        {[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} {n === 1 ? 'Panel' : 'Paneles'}</option>)}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 mb-3 uppercase tracking-widest">Estilo de Layout</label>
                                <div className="grid grid-cols-3 gap-3">
                                    {['dynamic', 'grid', 'vertical'].map(style => (
                                        <button
                                            key={style}
                                            onClick={() => setLayoutSettings({ ...layoutSettings, layout_style: style })}
                                            className={`py-3 rounded-xl border text-[10px] font-black uppercase tracking-tighter transition-all ${layoutSettings.layout_style === style
                                                ? 'bg-purple-600 border-purple-500 text-white shadow-lg shadow-purple-500/20'
                                                : 'bg-gray-950 border-gray-800 text-gray-600 hover:border-gray-700'
                                                }`}
                                        >
                                            {style === 'dynamic' ? 'Dinámico' : style === 'grid' ? 'Grilla' : 'Vertical'}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 mt-4">
                                {(project?.pages?.length > 0) ? (
                                    <>
                                        <button
                                            onClick={() => {
                                                // Sync settings but skip agent to just open the editor
                                                onStartGeneration({
                                                    max_pages: project.max_pages,
                                                    layout_style: project.layout_style,
                                                    plan_only: true,
                                                    skip_agent: true
                                                });
                                                setIsLayoutModalOpen(false);
                                            }}
                                            className="bg-gray-800 hover:bg-gray-700 text-gray-300 py-4 rounded-2xl font-bold transition-all flex flex-col items-center justify-center gap-1 border border-gray-700"
                                        >
                                            <span className="text-[10px] uppercase tracking-widest text-gray-500">Continuar</span>
                                            ABRIR EDITOR
                                        </button>
                                        <button
                                            onClick={() => {
                                                // Clear and start new wireframe
                                                onStartGeneration({ ...layoutSettings, plan_only: true });
                                                setIsLayoutModalOpen(false);
                                            }}
                                            className="bg-gray-800 hover:bg-gray-700 text-purple-400 py-4 rounded-2xl font-bold transition-all flex flex-col items-center justify-center gap-1 border border-purple-900/50"
                                        >
                                            <span className="text-[10px] uppercase tracking-widest text-purple-600">Nueva Escritura</span>
                                            REORGANIZAR
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        onClick={() => {
                                            onStartGeneration({ ...layoutSettings, plan_only: true });
                                            setIsLayoutModalOpen(false);
                                        }}
                                        className="bg-gray-800 hover:bg-gray-700 text-gray-300 py-5 rounded-2xl font-bold transition-all flex flex-col items-center justify-center gap-1 border border-gray-700 col-span-1"
                                    >
                                        <span className="text-xs uppercase tracking-widest text-gray-500">Paso 1</span>
                                        DISEÑAR MAQUETACIÓN
                                    </button>
                                )}
                                <button
                                    onClick={() => {
                                        onStartGeneration(layoutSettings);
                                        setIsLayoutModalOpen(false);
                                    }}
                                    className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white py-5 rounded-2xl font-black transition-all shadow-xl shadow-purple-500/30 flex flex-col items-center justify-center gap-1 col-span-2"
                                >
                                    <span className="text-[10px] uppercase tracking-widest text-purple-200 opacity-60">
                                        {(project?.pages?.length > 0) ? "Borrar y Generar" : "Paso Directo"}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        <Zap size={16} fill="white" />
                                        GENERAR TODO
                                    </div>
                                </button>
                            </div>
                        </div>
                    </div>
                </div >
            )}
        </div >
    );
};

const AssetForm = ({ type, initialData, onSubmit, onCancel }) => {
    const [name, setName] = useState(initialData?.name || initialData?.title || '');
    const [description, setDescription] = useState(initialData?.description || initialData?.content || '');
    const [file, setFile] = useState(null);

    const handleSubmit = (e) => {
        e.preventDefault();
        const payload = {
            [type === 'note' ? 'title' : 'name']: name,
            [type === 'note' ? 'content' : 'description']: description,
            metadata: file ? { file_name: file.name } : initialData?.metadata || {}
        };
        onSubmit(payload);
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            <div>
                <label className="block text-xs font-bold text-gray-500 mb-2 uppercase tracking-widest">Nombre / Título</label>
                <input
                    className="w-full bg-gray-950 border border-gray-700 rounded-xl px-5 py-3 text-white focus:border-purple-500 outline-none"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                />
            </div>
            <div>
                <label className="block text-xs font-bold text-gray-500 mb-2 uppercase tracking-widest">Descripción / Contenido</label>
                <textarea
                    className="w-full bg-gray-950 border border-gray-700 rounded-xl px-5 py-3 text-white focus:border-purple-500 outline-none h-32 resize-none"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                />
            </div>
            <div>
                <label className="block text-xs font-bold text-gray-500 mb-2 uppercase tracking-widest">Archivo Adjunto (Opcional)</label>
                <div className="relative">
                    <input
                        type="file"
                        className="absolute inset-0 opacity-0 cursor-pointer"
                        onChange={e => setFile(e.target.files[0])}
                    />
                    <div className="w-full bg-gray-800 border border-gray-700 border-dashed rounded-xl py-4 px-5 flex items-center justify-between text-gray-400 text-sm">
                        <span>{file ? file.name : "Subir imagen o documento..."}</span>
                        <Upload size={18} />
                    </div>
                </div>
            </div>
            <div className="flex gap-4 pt-4">
                <button type="button" onClick={onCancel} className="flex-1 py-4 text-gray-500 font-bold hover:text-white transition-colors">Cancelar</button>
                <button type="submit" className="flex-1 bg-purple-600 hover:bg-purple-500 text-white py-4 rounded-xl font-black shadow-lg shadow-purple-500/20 transition-all uppercase">
                    Guardar
                </button>
            </div>
        </form>
    );
};

export default ProjectDashboard;
