import type {
	EstadoTrackingPedido,
	PaisOperacion,
	Pedido,
	Urgencia,
} from "../types/models.js";

export function filterBy<T>(
	items: T[],
	predicate: (item: T) => boolean,
): T[] {
	return items.filter(predicate);
}

export function sortBy<T>(
	items: T[],
	compareFn: (a: T, b: T) => number,
): T[] {
	return [...items].sort(compareFn);
}

export function groupBy<T, K extends string | number>(
	items: T[],
	keySelector: (item: T) => K,
): Record<K, T[]> {
	return items.reduce<Record<K, T[]>>((groups, item) => {
		const key: K = keySelector(item);
		const currentGroup: T[] = groups[key] ?? [];

		groups[key] = [...currentGroup, item];
		return groups;
	}, {} as Record<K, T[]>);
}

export interface CriteriosFiltroPedido {
	destino?: PaisOperacion;
	urgencia?: Urgencia;
	estadoTracking?: EstadoTrackingPedido;
	pesoMinKg?: number;
	pesoMaxKg?: number;
}

export type DireccionOrden = "asc" | "desc";

export type CampoOrdenPedido = "destino" | "pesoKg" | "urgencia" | "fechaCreacion";

export interface CriterioOrdenPedido {
	campo: CampoOrdenPedido;
	direccion: DireccionOrden;
}

const URGENCIA_RANK: Record<Urgencia, number> = {
	BAJA: 1,
	MEDIA: 2,
	ALTA: 3,
	URGENTE: 4,
};

function comparePedidoByCampo(a: Pedido, b: Pedido, campo: CampoOrdenPedido): number {
	if (campo === "pesoKg") {
		return a.pesoKg - b.pesoKg;
	}

	if (campo === "fechaCreacion") {
		return new Date(a.fechaCreacion).getTime() - new Date(b.fechaCreacion).getTime();
	}

	if (campo === "urgencia") {
		return URGENCIA_RANK[a.urgencia] - URGENCIA_RANK[b.urgencia];
	}

	return a.destino.localeCompare(b.destino);
}

export function filtrarPedidosPorCriterios(
	pedidos: Pedido[],
	criterios: CriteriosFiltroPedido,
): Pedido[] {
	return pedidos.filter((pedido: Pedido) => {
		if (criterios.destino !== undefined && pedido.destino !== criterios.destino) {
			return false;
		}

		if (criterios.urgencia !== undefined && pedido.urgencia !== criterios.urgencia) {
			return false;
		}

		if (
			criterios.estadoTracking !== undefined &&
			pedido.estadoTracking !== criterios.estadoTracking
		) {
			return false;
		}

		if (criterios.pesoMinKg !== undefined && pedido.pesoKg < criterios.pesoMinKg) {
			return false;
		}

		if (criterios.pesoMaxKg !== undefined && pedido.pesoKg > criterios.pesoMaxKg) {
			return false;
		}

		return true;
	});
}

export function ordenarPedidosPorMultiplesCampos(
	pedidos: Pedido[],
	criteriosOrden: CriterioOrdenPedido[],
): Pedido[] {
	if (criteriosOrden.length === 0) {
		return [...pedidos];
	}

	return [...pedidos].sort((a: Pedido, b: Pedido) => {
		for (const criterio of criteriosOrden) {
			// Se aplica prioridad lexicografica: el primer criterio que diferencia decide el orden.
			const factor: number = criterio.direccion === "asc" ? 1 : -1;
			const comparacion: number = comparePedidoByCampo(a, b, criterio.campo);

			if (comparacion !== 0) {
				return comparacion * factor;
			}
		}

		return 0;
	});
}
