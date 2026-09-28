/** Globe canvas geometry, shared by the SSR-safe wrapper and the client-only WebGL component.
 *  (Kept out of GlobeInner so importing it never pulls three.js / react-globe.gl into SSR.)
 *  The canvas is CANVAS_W_R * R wide and CANVAS_H_R * R tall; the globe centre sits at the canvas
 *  centre and its on-screen radius is exactly R. */
export const CANVAS_W_R = 3.4;
export const CANVAS_H_R = 2.6;
