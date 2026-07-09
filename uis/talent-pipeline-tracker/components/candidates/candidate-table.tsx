import Link from "next/link";
import { CandidateRecord } from "@/types/candidates";
import { getStageLabel, getStatusBadgeClass, getStatusLabel } from "@/lib/candidate-domain";

interface CandidateTableProps {
  records: CandidateRecord[];
  total: number;
  loading: boolean;
  error: string | null;
}

export function CandidateTable({ records, total, loading, error }: CandidateTableProps) {
  return (
    <section className="card p-4">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="font-semibold">Candidaturas</h2>
        <p className="text-sm muted">Total: {total}</p>
      </div>

      {loading ? <p className="text-sm">Cargando candidaturas...</p> : null}
      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}

      {!loading && !error && records.length === 0 ? (
        <p className="text-sm muted">No hay candidaturas para los filtros seleccionados.</p>
      ) : null}

      {!loading && !error && records.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-left">
                <th className="py-2 pr-4 font-semibold">Nombre</th>
                <th className="py-2 pr-4 font-semibold">Puesto</th>
                <th className="py-2 pr-4 font-semibold">Estado</th>
                <th className="py-2 pr-4 font-semibold">Etapa</th>
                <th className="py-2 pr-4 font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id} className="border-b border-[var(--surface-soft)] align-top">
                  <td className="py-3 pr-4">
                    <p className="font-medium">{record.full_name}</p>
                    <p className="muted">{record.email}</p>
                  </td>
                  <td className="py-3 pr-4">{record.position}</td>
                  <td className="py-3 pr-4">
                    <span className={getStatusBadgeClass(record.status)}>{getStatusLabel(record.status)}</span>
                  </td>
                  <td className="py-3 pr-4">{getStageLabel(record.stage)}</td>
                  <td className="py-3 pr-4">
                    <Link
                      href={`/candidates/${record.id}`}
                      className="btn btn-secondary inline-flex items-center"
                    >
                      Ver detalle
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
