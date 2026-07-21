import {
  CONSULTAS_EJEMPLO,
  DEVOLUCIONES_EJEMPLO,
  INCIDENCIAS_EJEMPLO,
  PEDIDOS_EJEMPLO,
  TRANSPORTISTAS_EJEMPLO,
} from "../../../src/types/models";
import { filtrarPedidosPorCriterios } from "../../../src/utils/collections";
import { buscarPedidoLinealPorId } from "../../../src/utils/search";
import {
  calcularPesoPromedioPedidos,
  generarReporteTrackFlow,
  type ReporteTrackFlow,
} from "../../../src/utils/transformations";
import {
  validarConsultaCliente,
  validarPedido,
  validarTransportista,
} from "../../../src/utils/validations";

interface ValidationIssue {
  entity: string;
  id: string;
  errors: string[];
}

export interface DashboardSnapshot {
  report: ReporteTrackFlow;
  pedidosUrgentesNoEntregados: number;
  pedidoBuscado: string;
  pesoPromedio: number;
  consultasAutomaticas: number;
  validationIssues: ValidationIssue[];
}

export function buildDashboardSnapshot(): DashboardSnapshot {
  const report = generarReporteTrackFlow(
    PEDIDOS_EJEMPLO,
    CONSULTAS_EJEMPLO,
    DEVOLUCIONES_EJEMPLO,
    INCIDENCIAS_EJEMPLO,
  );

  const pedidosUrgentesNoEntregados = filtrarPedidosPorCriterios(PEDIDOS_EJEMPLO, {
    urgencia: "URGENTE",
  }).filter((pedido) => pedido.estadoTracking !== "ENTREGADO").length;

  const pedidoBuscado = buscarPedidoLinealPorId(PEDIDOS_EJEMPLO, "P-1003")?.estadoTracking ?? "NO_ENCONTRADO";

  const pesoPromedio = calcularPesoPromedioPedidos(PEDIDOS_EJEMPLO);

  const consultasAutomaticas = CONSULTAS_EJEMPLO.filter(
    (consulta) => consulta.estadoAgente === "RESPONDIDA_AUTOMATICAMENTE",
  ).length;

  const validationIssues: ValidationIssue[] = [
    ...PEDIDOS_EJEMPLO.map((pedido) => ({
      entity: "Pedido",
      id: pedido.idPedido,
      errors: validarPedido(pedido),
    })),
    ...TRANSPORTISTAS_EJEMPLO.map((transportista) => ({
      entity: "Transportista",
      id: transportista.idTransportista,
      errors: validarTransportista(transportista),
    })),
    ...CONSULTAS_EJEMPLO.map((consulta) => ({
      entity: "Consulta",
      id: consulta.idConsulta,
      errors: validarConsultaCliente(consulta),
    })),
  ].filter((issue) => issue.errors.length > 0);

  return {
    report,
    pedidosUrgentesNoEntregados,
    pedidoBuscado,
    pesoPromedio,
    consultasAutomaticas,
    validationIssues,
  };
}
