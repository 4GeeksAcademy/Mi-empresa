import { CandidateStage, CandidateStatus } from "@/types/candidates";

export const STATUS_OPTIONS: { value: CandidateStatus; label: string }[] = [
  { value: "received", label: "Recibida" },
  { value: "in_progress", label: "En proceso" },
  { value: "selected", label: "Seleccionada" },
  { value: "discarded", label: "Descartada" },
];

export const STAGE_OPTIONS: { value: CandidateStage; label: string }[] = [
  { value: "pending", label: "Pendiente" },
  { value: "review", label: "Revisión" },
  { value: "personal_interview", label: "Entrevista personal" },
  { value: "technical_interview", label: "Entrevista técnica" },
  { value: "offer_presented", label: "Oferta presentada" },
];

const statusMap = new Map(STATUS_OPTIONS.map((option) => [option.value, option.label]));
const stageMap = new Map(STAGE_OPTIONS.map((option) => [option.value, option.label]));

export function getStatusLabel(value: string): string {
  return statusMap.get(value as CandidateStatus) ?? value;
}

export function getStageLabel(value: string): string {
  return stageMap.get(value as CandidateStage) ?? value;
}

export function getStatusBadgeClass(status: string): string {
  switch (status) {
    case "received":
      return "badge badge-received";
    case "in_progress":
      return "badge badge-in-progress";
    case "selected":
      return "badge badge-selected";
    case "discarded":
      return "badge badge-discarded";
    default:
      return "badge";
  }
}
