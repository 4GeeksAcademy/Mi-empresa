"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CandidateNote } from "@/types/candidates";
import { createCandidateNote, deleteCandidateNote, getCandidateNotes } from "@/services/candidates";
import { formatDate } from "@/lib/format";

interface CandidateNotesProps {
  recordId: string;
}

export function CandidateNotes({ recordId }: CandidateNotesProps) {
  const [notes, setNotes] = useState<CandidateNote[]>([]);
  const [newContent, setNewContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadNotes = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const payload = await getCandidateNotes(recordId);
      setNotes(payload.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudieron cargar las notas.");
    } finally {
      setLoading(false);
    }
  }, [recordId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadNotes();
  }, [loadNotes]);

  async function handleCreateNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccess(null);
    setError(null);

    if (!newContent.trim()) {
      setError("La nota no puede estar vacía.");
      return;
    }

    setSaving(true);
    try {
      await createCandidateNote(recordId, { content: newContent.trim() });
      setNewContent("");
      setSuccess("Nota guardada correctamente.");
      await loadNotes();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "No se pudo guardar la nota.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteNote(noteId: string) {
    setSuccess(null);
    setError(null);
    try {
      await deleteCandidateNote(recordId, noteId);
      setSuccess("Nota eliminada.");
      await loadNotes();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "No se pudo eliminar la nota.");
    }
  }

  return (
    <section className="card p-4 space-y-3">
      <h2 className="text-lg font-semibold">Notas internas</h2>

      {success ? <p className="text-sm text-[var(--ok)]">{success}</p> : null}
      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}

      <form className="space-y-2" onSubmit={handleCreateNote}>
        <label className="text-sm block">
          Nueva nota
          <textarea
            className="input mt-1 min-h-24"
            value={newContent}
            onChange={(event) => setNewContent(event.target.value)}
            placeholder="Añade contexto para el siguiente entrevistador"
          />
        </label>
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? "Guardando..." : "Guardar nota"}
        </button>
      </form>

      {loading ? <p className="text-sm">Cargando notas...</p> : null}

      {!loading && notes.length === 0 ? <p className="text-sm muted">No hay notas todavía.</p> : null}

      {!loading && notes.length > 0 ? (
        <ul className="space-y-2">
          {notes.map((note) => (
            <li key={note.id} className="border border-[var(--border)] rounded-xl p-3">
              <p className="text-sm whitespace-pre-wrap">{note.content}</p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="text-xs muted">Creada: {formatDate(note.created_at)}</p>
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={() => {
                    void handleDeleteNote(note.id);
                  }}
                >
                  Eliminar
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
