import {
	CONSULTAS_EJEMPLO,
	DEVOLUCIONES_EJEMPLO,
	INCIDENCIAS_EJEMPLO,
	PEDIDOS_EJEMPLO,
	TRANSPORTISTAS_EJEMPLO,
	type Pedido,
} from "../types/models.js";
import {
	filtrarPedidosPorCriterios,
	filterBy,
	groupBy,
	ordenarPedidosPorMultiplesCampos,
	sortBy,
} from "../utils/collections.js";
import {
	buscarPedidoBinarioPorPeso,
	buscarPedidoLinealPorId,
	binarySearchByNumber,
	linearSearch,
} from "../utils/search.js";
import {
	averageBy,
	calcularPesoPromedioPedidos,
	calcularPesoTotalPedidos,
	contarConsultasPorTipo,
	countByCategory,
	generarReporteTrackFlow,
	maxBy,
	minBy,
	obtenerPedidoMayorPeso,
	obtenerPedidoMenorPeso,
	sumBy,
} from "../utils/transformations.js";
import {
	validarConsultaCliente,
	validarDevolucion,
	validarIncidenciaTransportista,
	validarPedido,
	validarPedidoConTransportista,
	validarTransportista,
} from "../utils/validations.js";

describe("busquedas de pedidos", () => {
	it("encuentra pedidos y devuelve null cuando no existe una coincidencia", () => {
		const byWeight = [...PEDIDOS_EJEMPLO].sort((first, second) => first.pesoKg - second.pesoKg);

		expect(linearSearch(PEDIDOS_EJEMPLO, (pedido) => pedido.idPedido === "P-1002"))
			.toMatchObject({ idPedido: "P-1002" });
		expect(buscarPedidoLinealPorId(PEDIDOS_EJEMPLO, "missing")).toBeNull();
		expect(binarySearchByNumber(byWeight, 2.4, (pedido) => pedido.pesoKg))
			.toMatchObject({ idPedido: "P-1001" });
		expect(buscarPedidoBinarioPorPeso(byWeight, 99)).toBeNull();
	});
});

describe("colecciones de pedidos", () => {
	it("filtra, agrupa y ordena sin mutar la lista original", () => {
		const original = [...PEDIDOS_EJEMPLO];
		const filtered = filterBy(PEDIDOS_EJEMPLO, (pedido) => pedido.destino === "ES");
		const grouped = groupBy(PEDIDOS_EJEMPLO, (pedido) => pedido.destino);
		const sorted = sortBy(PEDIDOS_EJEMPLO, (first, second) => first.pesoKg - second.pesoKg);

		expect(filtered).toHaveLength(2);
		expect(grouped.ES.map((pedido) => pedido.idPedido)).toEqual(["P-1002", "P-1003"]);
		expect(sorted.map((pedido) => pedido.idPedido)).toEqual(["P-1002", "P-1001", "P-1003"]);
		expect(PEDIDOS_EJEMPLO).toEqual(original);
	});

	it("aplica limites inclusivos y prioridad de ordenacion", () => {
		const filtered = filtrarPedidosPorCriterios(PEDIDOS_EJEMPLO, {
			destino: "US",
			pesoMinKg: 2.4,
			pesoMaxKg: 2.4,
		});
		const ordered = ordenarPedidosPorMultiplesCampos(PEDIDOS_EJEMPLO, [
			{ campo: "destino", direccion: "asc" },
			{ campo: "pesoKg", direccion: "desc" },
		]);

		expect(filtered.map((pedido) => pedido.idPedido)).toEqual(["P-1001"]);
		expect(ordenarPedidosPorMultiplesCampos(PEDIDOS_EJEMPLO, [])).toEqual(PEDIDOS_EJEMPLO);
		expect(ordered.map((pedido) => pedido.idPedido)).toEqual(["P-1003", "P-1002", "P-1001"]);
	});
});

describe("agregaciones operativas", () => {
	it("calcula totales, extremos y categorias incluyendo categorias sin consultas", () => {
		const report = generarReporteTrackFlow(
			PEDIDOS_EJEMPLO,
			CONSULTAS_EJEMPLO,
			DEVOLUCIONES_EJEMPLO,
			INCIDENCIAS_EJEMPLO,
		);

		expect(countByCategory(CONSULTAS_EJEMPLO, (consulta) => consulta.idioma)).toEqual({ es: 1, en: 1 });
		expect(sumBy(PEDIDOS_EJEMPLO, (pedido) => pedido.pesoKg)).toBe(8.3);
		expect(averageBy([], (value: number) => value)).toBe(0);
		expect(maxBy([], (value: number) => value)).toBeNull();
		expect(minBy([], (value: number) => value)).toBeNull();
		expect(calcularPesoTotalPedidos(PEDIDOS_EJEMPLO)).toBe(8.3);
		expect(calcularPesoPromedioPedidos(PEDIDOS_EJEMPLO)).toBeCloseTo(8.3 / 3);
		expect(obtenerPedidoMayorPeso(PEDIDOS_EJEMPLO)?.idPedido).toBe("P-1003");
		expect(obtenerPedidoMenorPeso(PEDIDOS_EJEMPLO)?.idPedido).toBe("P-1002");
		expect(report).toMatchObject({ totalPedidos: 3, totalConsultas: 2, consultasPorTipo: { PEDIDO: 0, TRACKING: 1, DEVOLUCION: 1, INCIDENCIA: 0 } });
	});
});

describe("validaciones de trazabilidad", () => {
	it("acepta registros consistentes", () => {
		expect(validarTransportista(TRANSPORTISTAS_EJEMPLO[0]!)).toEqual([]);
		expect(validarPedido(PEDIDOS_EJEMPLO[1]!)).toEqual([]);
		expect(validarPedidoConTransportista(PEDIDOS_EJEMPLO[0]!, TRANSPORTISTAS_EJEMPLO[0]!)).toEqual([]);
		expect(validarDevolucion(DEVOLUCIONES_EJEMPLO[0]!)).toEqual([]);
		expect(validarIncidenciaTransportista(INCIDENCIAS_EJEMPLO[0]!)).toEqual([]);
		expect(validarConsultaCliente(CONSULTAS_EJEMPLO[1]!)).toEqual([]);
	});

	it("rechaza estados y datos incompatibles", () => {
		const invalidDelivered: Pedido = { ...PEDIDOS_EJEMPLO[1]!, fechaEntregaReal: null };
		const invalidCarrier = { ...TRANSPORTISTAS_EJEMPLO[0]!, activo: false, pesoMaximoKg: 1 };
		const invalidReturn = { ...DEVOLUCIONES_EJEMPLO[0]!, estadoDevolucion: "CERRADA" as const };
		const invalidIncident = { ...INCIDENCIAS_EJEMPLO[0]!, estadoIncidencia: "RESUELTA" as const, fechaResolucion: null };
		const invalidQuery = { ...CONSULTAS_EJEMPLO[0]!, idPedido: null, estadoAgente: "RESPONDIDA_AUTOMATICAMENTE" as const, respuestaAutomatica: null };

		expect(validarPedido(invalidDelivered)).toContain("Pedido ENTREGADO requiere fechaEntregaReal valida");
		expect(validarPedidoConTransportista(PEDIDOS_EJEMPLO[0]!, invalidCarrier)).toEqual(expect.arrayContaining([
			"El transportista debe estar activo para asignar pedidos",
			"El pedido supera el peso permitido por el transportista para la seleccion por peso",
		]));
		expect(validarDevolucion(invalidReturn)).toContain("Devolucion en estado final requiere fechaResolucion");
		expect(validarIncidenciaTransportista(invalidIncident)).toContain("IncidenciaTransportista RESUELTA requiere fechaResolucion valida");
		expect(validarConsultaCliente(invalidQuery)).toEqual(expect.arrayContaining([
			"ConsultaCliente.idPedido es obligatorio para consultas de pedido, tracking, devolucion o incidencia",
			"ConsultaCliente RESPONDIDA_AUTOMATICAMENTE requiere respuestaAutomatica",
		]));
	});
});