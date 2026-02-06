import React, { useState, useEffect } from 'react';
import EditorCanvas from './components/EditorCanvas';
import { Loader2, Zap, Save, Download, RefreshCw } from 'lucide-react';
import axios from 'axios';

function App() {
    const [loading, setLoading] = useState(false);
    const [panels, setPanels] = useState([]);
    const [projectId] = useState("df81774e-5612-4c6e-88c9-5a1e8a9f6d4a");

    const fetchPanels = async () => {
        try {
            const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);
            setPanels(response.data.panels);
        } catch (error) {
            console.error("Error fetching panels:", error);
        }
    };

    useEffect(() => {
        fetchPanels();
    }, []);

    const handleGenerate = async () => {
        setLoading(true);
        try {
            await axios.post(`${import.meta.env.VITE_API_URL}/projects/${projectId}/generate/`);
            // Iniciamos polling para ver los cambios
            const interval = setInterval(async () => {
                const response = await axios.get(`${import.meta.env.VITE_API_URL}/projects/${projectId}/`);
                if (response.data.panels.length > 0) {
                    setPanels(response.data.panels);
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
        <div className="flex h-screen bg-black text-white overflow-hidden">
            {/* Sidebar de Control */}
            <div className="w-80 bg-gray-900 border-r border-gray-800 p-6 flex flex-col gap-6">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-pink-600 bg-clip-text text-transparent">
                    ComicDraft AI
                </h1>

                <button
                    onClick={handleGenerate}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-lg shadow-purple-900/20"
                >
                    {loading ? <Loader2 className="animate-spin" /> : <Zap size={20} />}
                    {loading ? "Generando..." : "Generar Borrador"}
                </button>

                <div className="border-t border-gray-800 pt-6">
                    <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Exportar Pantalla</h2>
                    <div className="grid grid-cols-2 gap-3">
                        <button className="flex flex-col items-center gap-2 p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition">
                            <Download size={20} />
                            <span className="text-xs">PDF</span>
                        </button>
                        <button className="flex flex-col items-center gap-2 p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition">
                            <Save size={20} />
                            <span className="text-xs">Guardar</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Area del Editor */}
            <div className="flex-1 overflow-auto bg-gray-950 flex justify-center py-10">
                <EditorCanvas panels={panels} />
            </div>
        </div>
    );
}

export default App;
