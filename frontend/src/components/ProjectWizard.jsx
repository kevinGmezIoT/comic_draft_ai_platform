import React, { useState } from 'react';
import {
    ChevronRight, ChevronLeft, Upload, Users, Map,
    FileText, Save, Plus, Trash2, Check, Loader2
} from 'lucide-react';
import axios from 'axios';

const ProjectWizard = ({ onComplete }) => {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [projectData, setProjectData] = useState({
        name: '',
        description: '',
        worldBible: '',
        styleGuide: '',
        scriptFile: null,
        characters: [],
        sceneries: []
    });

    const [newCharacter, setNewCharacter] = useState({ name: '', description: '', file: null });
    const [newScenery, setNewScenery] = useState({ name: '', description: '', file: null });

    const handleNext = () => setStep(prev => prev + 1);
    const handleBack = () => setStep(prev => prev - 1);

    const handleCreateProject = async () => {
        setLoading(true);
        try {
            // 1. Create Project
            const projectRes = await axios.post(`${import.meta.env.VITE_API_URL}/projects/`, {
                name: projectData.name,
                description: projectData.description,
                world_bible: projectData.worldBible,
                style_guide: projectData.styleGuide
            });
            const projectId = projectRes.data.id;

            // 2. Create Characters
            for (const char of projectData.characters) {
                await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/characters/create/`, {
                    name: char.name,
                    description: char.description,
                    metadata: { file_name: char.file ? char.file.name : null }
                });
            }

            // 3. Create Sceneries
            for (const scene of projectData.sceneries) {
                await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/sceneries/create/`, {
                    name: scene.name,
                    description: scene.description,
                    metadata: { file_name: scene.file ? scene.file.name : null }
                });
            }

            onComplete(projectId);
        } catch (error) {
            console.error("Error creating project:", error);
            alert("Error al crear el proyecto");
        } finally {
            setLoading(false);
        }
    };

    const addCharacter = () => {
        if (newCharacter.name) {
            setProjectData(prev => ({
                ...prev,
                characters: [...prev.characters, newCharacter]
            }));
            setNewCharacter({ name: '', description: '', file: null });
        }
    };

    const addScenery = () => {
        if (newScenery.name) {
            setProjectData(prev => ({
                ...prev,
                sceneries: [...prev.sceneries, newScenery]
            }));
            setNewScenery({ name: '', description: '', file: null });
        }
    };

    const removeCharacter = (idx) => {
        setProjectData(prev => ({
            ...prev,
            characters: prev.characters.filter((_, i) => i !== idx)
        }));
    };

    const removeScenery = (idx) => {
        setProjectData(prev => ({
            ...prev,
            sceneries: prev.sceneries.filter((_, i) => i !== idx)
        }));
    };

    return (
        <div className="w-full max-w-4xl bg-gray-900 border border-gray-800 rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-500">
            {/* Header / Stepper */}
            <div className="bg-gray-800/50 p-8 border-b border-gray-800">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Nuevo Proyecto de Cómic</h2>
                        <p className="text-gray-400 text-sm mt-1">Configura las bases de tu historia</p>
                    </div>
                    <div className="flex gap-2">
                        {[1, 2, 3, 4, 5].map(s => (
                            <div
                                key={s}
                                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 ${step === s ? 'bg-purple-600 text-white scale-110 shadow-lg shadow-purple-500/20' :
                                    step > s ? 'bg-green-600 text-white' : 'bg-gray-700 text-gray-500'
                                    }`}
                            >
                                {step > s ? <Check size={14} /> : s}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="flex items-center gap-4 text-[10px] font-bold uppercase tracking-widest overflow-x-auto pb-2">
                    <span className={step === 1 ? 'text-purple-400 whitespace-nowrap' : 'text-gray-500 whitespace-nowrap'}>Información</span>
                    <ChevronRight size={14} className="text-gray-700 shrink-0" />
                    <span className={step === 2 ? 'text-purple-400 whitespace-nowrap' : 'text-gray-500 whitespace-nowrap'}>Guión</span>
                    <ChevronRight size={14} className="text-gray-700 shrink-0" />
                    <span className={step === 3 ? 'text-purple-400 whitespace-nowrap' : 'text-gray-500 whitespace-nowrap'}>Personajes</span>
                    <ChevronRight size={14} className="text-gray-700 shrink-0" />
                    <span className={step === 4 ? 'text-purple-400 whitespace-nowrap' : 'text-gray-500 whitespace-nowrap'}>Escenarios</span>
                    <ChevronRight size={14} className="text-gray-700 shrink-0" />
                    <span className={step === 5 ? 'text-purple-400 whitespace-nowrap' : 'text-gray-500 whitespace-nowrap'}>Biblia / Estilo</span>
                </div>
            </div>

            {/* Content */}
            <div className="p-10 min-h-[450px]">
                {step === 1 && (
                    <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                        <div className="grid gap-6">
                            <div>
                                <label className="block text-sm font-bold text-gray-400 mb-2 uppercase tracking-wide">Nombre del Cómic</label>
                                <input
                                    type="text"
                                    className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all text-lg"
                                    placeholder="Ej: Crónicas del Vacío"
                                    value={projectData.name}
                                    onChange={e => setProjectData({ ...projectData, name: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-bold text-gray-400 mb-2 uppercase tracking-wide">Sinopsis / Descripción</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all h-32 resize-none"
                                    placeholder="Describe brevemente de qué trata tu historia..."
                                    value={projectData.description}
                                    onChange={e => setProjectData({ ...projectData, description: e.target.value })}
                                />
                            </div>
                        </div>
                    </div>
                )}

                {step === 2 && (
                    <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                        <div className="flex flex-col items-center justify-center border-2 border-dashed border-gray-700 rounded-3xl p-12 bg-gray-950/50 hover:bg-gray-900 transition-colors group cursor-pointer relative">
                            <input
                                type="file"
                                className="absolute inset-0 opacity-0 cursor-pointer"
                                accept=".pdf,.docx,.txt"
                                onChange={e => setProjectData({ ...projectData, scriptFile: e.target.files[0] })}
                            />
                            <div className="w-20 h-20 bg-gray-800 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-purple-600/20 group-hover:text-purple-400 transition-all">
                                <FileText size={40} className="text-gray-500 group-hover:text-purple-400 transition-all" />
                            </div>
                            <h3 className="text-xl font-bold text-white mb-2">Sube tu Guión</h3>
                            <p className="text-gray-500 text-center max-w-sm mb-6">
                                Aceptamos archivos PDF, DOCX o TXT con la estructura de tu cómic.
                            </p>
                            <div className="bg-gray-800 hover:bg-gray-700 text-white px-8 py-3 rounded-xl font-bold transition-all border border-gray-700">
                                Seleccionar Archivo
                            </div>
                            {projectData.scriptFile && (
                                <div className="mt-6 flex items-center gap-2 text-green-400 bg-green-400/10 px-4 py-2 rounded-lg">
                                    <Check size={16} />
                                    <span className="text-sm font-medium">{projectData.scriptFile.name}</span>
                                    <button onClick={(e) => {
                                        e.preventDefault();
                                        setProjectData({ ...projectData, scriptFile: null });
                                    }} className="ml-2 text-gray-500 hover:text-red-400">
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {step === 3 && (
                    <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                        <div className="grid grid-cols-2 gap-8">
                            <div className="space-y-6">
                                <h3 className="text-lg font-bold text-purple-400 flex items-center gap-2">
                                    <Users size={20} />
                                    Nuevo Personaje
                                </h3>
                                <div className="bg-gray-800/30 p-6 rounded-2xl border border-gray-800 space-y-4">
                                    <input
                                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-white focus:border-purple-500 outline-none"
                                        placeholder="Nombre del personaje"
                                        value={newCharacter.name}
                                        onChange={e => setNewCharacter({ ...newCharacter, name: e.target.value })}
                                    />
                                    <textarea
                                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white focus:border-purple-500 outline-none h-24 resize-none"
                                        placeholder="Descripción física, rasgos clave..."
                                        value={newCharacter.description}
                                        onChange={e => setNewCharacter({ ...newCharacter, description: e.target.value })}
                                    />
                                    <div className="relative">
                                        <input
                                            type="file"
                                            className="absolute inset-0 opacity-0 cursor-pointer"
                                            onChange={e => setNewCharacter({ ...newCharacter, file: e.target.files[0] })}
                                        />
                                        <div className="w-full bg-gray-900 border border-gray-700 border-dashed rounded-xl py-2 px-4 flex items-center justify-between text-xs text-gray-500">
                                            <span>{newCharacter.file ? newCharacter.file.name : "Adjuntar referencia (opcional)"}</span>
                                            <Upload size={14} />
                                        </div>
                                    </div>
                                    <button
                                        onClick={addCharacter}
                                        className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg hover:shadow-purple-500/20 flex items-center justify-center gap-2"
                                    >
                                        <Plus size={18} />
                                        Añadir Personaje
                                    </button>
                                </div>
                            </div>
                            <div className="space-y-4">
                                <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest">Registrados ({projectData.characters.length})</h3>
                                <div className="space-y-3 max-h-[300px] overflow-auto pr-2">
                                    {projectData.characters.length === 0 ? (
                                        <div className="text-gray-600 text-center py-12 bg-gray-950/30 rounded-2xl border border-dashed border-gray-800">
                                            Sin personajes aún
                                        </div>
                                    ) : (
                                        projectData.characters.map((char, i) => (
                                            <div key={i} className="flex items-center justify-between p-4 bg-gray-800/50 rounded-xl border border-gray-800 animate-in slide-in-from-bottom-2 duration-200">
                                                <div className="flex-1 overflow-hidden mr-4">
                                                    <p className="font-bold text-white truncate">{char.name}</p>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        {char.file && <FileText size={10} className="text-purple-400" />}
                                                        <p className="text-[10px] text-gray-500 truncate">{char.description}</p>
                                                    </div>
                                                </div>
                                                <button onClick={() => removeCharacter(i)} className="text-gray-500 hover:text-red-400 transition-colors p-2 flex-shrink-0">
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {step === 4 && (
                    <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                        <div className="grid grid-cols-2 gap-8">
                            <div className="space-y-6">
                                <h3 className="text-lg font-bold text-purple-400 flex items-center gap-2">
                                    <Map size={20} />
                                    Nuevo Escenario
                                </h3>
                                <div className="bg-gray-800/30 p-6 rounded-2xl border border-gray-800 space-y-4">
                                    <input
                                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-white focus:border-purple-500 outline-none"
                                        placeholder="Nombre del lugar"
                                        value={newScenery.name}
                                        onChange={e => setNewScenery({ ...newScenery, name: e.target.value })}
                                    />
                                    <textarea
                                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white focus:border-purple-500 outline-none h-24 resize-none"
                                        placeholder="Atmósfera, detalles..."
                                        value={newScenery.description}
                                        onChange={e => setNewScenery({ ...newScenery, description: e.target.value })}
                                    />
                                    <div className="relative">
                                        <input
                                            type="file"
                                            className="absolute inset-0 opacity-0 cursor-pointer"
                                            onChange={e => setNewScenery({ ...newScenery, file: e.target.files[0] })}
                                        />
                                        <div className="w-full bg-gray-900 border border-gray-700 border-dashed rounded-xl py-2 px-4 flex items-center justify-between text-xs text-gray-500">
                                            <span>{newScenery.file ? newScenery.file.name : "Subir mapa o boceto (opcional)"}</span>
                                            <Upload size={14} />
                                        </div>
                                    </div>
                                    <button
                                        onClick={addScenery}
                                        className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg hover:shadow-purple-500/20 flex items-center justify-center gap-2"
                                    >
                                        <Plus size={18} />
                                        Añadir al Mundo
                                    </button>
                                </div>
                            </div>
                            <div className="space-y-4">
                                <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest">Escenarios ({projectData.sceneries.length})</h3>
                                <div className="space-y-3 max-h-[300px] overflow-auto pr-2">
                                    {projectData.sceneries.length === 0 ? (
                                        <div className="text-gray-600 text-center py-12 bg-gray-950/30 rounded-2xl border border-dashed border-gray-800">
                                            Sin lugares registrados
                                        </div>
                                    ) : (
                                        projectData.sceneries.map((scene, i) => (
                                            <div key={i} className="flex items-center justify-between p-4 bg-gray-800/50 rounded-xl border border-gray-800 animate-in slide-in-from-bottom-2 duration-200">
                                                <div className="flex-1 overflow-hidden mr-4">
                                                    <p className="font-bold text-white truncate">{scene.name}</p>
                                                    <p className="text-[10px] text-gray-500 truncate">{scene.description}</p>
                                                </div>
                                                <button onClick={() => removeScenery(i)} className="text-gray-500 hover:text-red-400 transition-colors p-2 flex-shrink-0">
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {step === 5 && (
                    <div className="space-y-8 animate-in slide-in-from-right-4 duration-300">
                        <div className="grid gap-8">
                            <div>
                                <h3 className="text-lg font-bold text-purple-400 flex items-center gap-2 mb-4">
                                    <Save size={20} />
                                    Biblia del Mundo / Contexto Global
                                </h3>
                                <p className="text-sm text-gray-500 mb-6">Información que estará presente en cada rincón del cómic: nombres recurrentes, amigos, relaciones, localización global, etc.</p>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-4 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all h-40 resize-none font-mono text-sm"
                                    placeholder="Ej: La ciudad de Neo-Tokio siempre tiene lluvia dorada. El protagonista tiene un perro llamado Volt que aparece con frecuencia..."
                                    value={projectData.worldBible}
                                    onChange={e => setProjectData({ ...projectData, worldBible: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-500 mb-3 uppercase tracking-widest">Guía de Estilo Visual / Paleta de Colores</label>
                                <textarea
                                    className="w-full bg-gray-950 border border-gray-700 rounded-2xl px-6 py-3 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all h-24 resize-none text-sm"
                                    placeholder="Ej: Tonos pastel, estilo acuarela, líneas gruesas noir, predominio del azul y neón..."
                                    value={projectData.styleGuide}
                                    onChange={e => setProjectData({ ...projectData, styleGuide: e.target.value })}
                                />
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Footer / Nav */}
            <div className="bg-gray-800/50 p-8 border-t border-gray-800 flex justify-between items-center">
                <button
                    onClick={handleBack}
                    disabled={step === 1 || loading}
                    className="flex items-center gap-2 text-gray-400 hover:text-white font-bold disabled:opacity-0 transition-opacity"
                >
                    <ChevronLeft size={20} />
                    Atrás
                </button>

                {step < 5 ? (
                    <button
                        onClick={handleNext}
                        disabled={step === 1 && !projectData.name}
                        className="bg-white text-black hover:bg-gray-200 px-10 py-3 rounded-2xl font-bold transition-all flex items-center gap-2 shadow-xl hover:shadow-white/10 disabled:bg-gray-600 disabled:text-gray-400"
                    >
                        Siguiente
                        <ChevronRight size={20} />
                    </button>
                ) : (
                    <button
                        onClick={handleCreateProject}
                        disabled={loading}
                        className="bg-purple-600 hover:bg-purple-700 text-white px-10 py-4 rounded-2xl font-bold transition-all flex items-center gap-2 shadow-xl shadow-purple-500/20 disabled:bg-gray-800"
                    >
                        {loading ? <Loader2 className="animate-spin" /> : <Save size={20} />}
                        {loading ? "Creando..." : "Crear Proyecto de Cómic"}
                    </button>
                )}
            </div>
        </div>
    );
};

export default ProjectWizard;
