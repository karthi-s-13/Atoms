export const GLOBAL_DIRECTIONS = Object.freeze(["NORTH", "EAST", "SOUTH", "WEST"]);

export const WORLD_DIRECTION_AXES = Object.freeze({
  NORTH: Object.freeze({ x: 0, z: -1 }),
  SOUTH: Object.freeze({ x: 0, z: 1 }),
  EAST: Object.freeze({ x: 1, z: 0 }),
  WEST: Object.freeze({ x: -1, z: 0 }),
});

export function directionAxis(direction, axes = WORLD_DIRECTION_AXES) {
  return axes?.[direction] ?? WORLD_DIRECTION_AXES[direction];
}

export function isVerticalDirection(direction) {
  return direction === "NORTH" || direction === "SOUTH";
}

function normalizeWorldVector(x, z) {
  const length = Math.hypot(x, z) || 1;
  return { x: x / length, z: z / length };
}

export function simulationToWorldPoint(point, elevation = 0) {
  return [point.x, elevation, -point.y];
}

export function simulationToWorldVector(vector) {
  return normalizeWorldVector(vector.x, -vector.y);
}

export function worldPointForDirection(direction, distance, elevation = 0, axes = WORLD_DIRECTION_AXES) {
  const axis = directionAxis(direction, axes);
  return [axis.x * distance, elevation, axis.z * distance];
}

export function worldYawFromSimulationHeading(heading = 0) {
  return Math.atan2(Math.sin(heading), -Math.cos(heading));
}

export function worldYawFromSimulationVector(x, y) {
  const direction = simulationToWorldVector({ x, y });
  return Math.atan2(direction.x, direction.z);
}
