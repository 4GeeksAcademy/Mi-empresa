"use client";

import { CandidateStage, CandidateStatus } from "@/types/candidates";
import { STAGE_OPTIONS, STATUS_OPTIONS } from "@/lib/candidate-domain";

interface CandidateFiltersProps {
  status: CandidateStatus | "";
  stage: CandidateStage | "";
  search: string;
  onStatusChange: (status: CandidateStatus | "") => void;
  onStageChange: (stage: CandidateStage | "") => void;
  onSearchChange: (search: string) => void;
  onClear: () => void;
}

export function CandidateFilters({
  status,
  stage,
  search,
  onStatusChange,
  onStageChange,
  onSearchChange,
  onClear,
}: CandidateFiltersProps) {
  return (
    <section className="card p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">Filtros de búsqueda</h2>
        <button className="btn btn-secondary" type="button" onClick={onClear}>
          Limpiar
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="text-sm">
          Estado
          <select
            className="input mt-1"
            value={status}
            onChange={(event) => onStatusChange(event.target.value as CandidateStatus | "")}
          >
            <option value="">Todos</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          Etapa
          <select
            className="input mt-1"
            value={stage}
            onChange={(event) => onStageChange(event.target.value as CandidateStage | "")}
          >
            <option value="">Todas</option>
            {STAGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          Buscar por nombre o email
          <input
            className="input mt-1"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Ej: maria@empresa.com"
          />
        </label>
      </div>
    </section>
  );
}
