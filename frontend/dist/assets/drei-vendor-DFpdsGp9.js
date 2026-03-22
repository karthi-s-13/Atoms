import{a as Pt,r as U}from"./router-vendor-hp_kD9gk.js";import{g as Mt,c as x,M as K,h as q,i as Ve,Q as Ge,O as ye,d as z,P as Ee,j as Tt,k as Dt,I as jt,F as Ze,l as _e,m as $,n as Ut,o as Ae,p as at,q as Ct,r as Xe,s as Ke,t as zt,u as Q,v as It,w as Rt,x as Nt,y as Bt}from"./three-core-C1PYXih1.js";import{u as Y,a as Ht}from"./fiber-vendor-dziJrsY8.js";var qe={},$e=Pt;qe.createRoot=$e.createRoot,qe.hydrateRoot=$e.hydrateRoot;const kt="modulepreload",Ft=function(u){return"/"+u},Qe={},sn=function(n,i,e){let s=Promise.resolve();if(i&&i.length>0){document.getElementsByTagName("link");const p=document.querySelector("meta[property=csp-nonce]"),r=(p==null?void 0:p.nonce)||(p==null?void 0:p.getAttribute("nonce"));s=Promise.allSettled(i.map(c=>{if(c=Ft(c),c in Qe)return;Qe[c]=!0;const S=c.endsWith(".css"),h=S?'[rel="stylesheet"]':"";if(document.querySelector(`link[href="${c}"]${h}`))return;const f=document.createElement("link");if(f.rel=S?"stylesheet":kt,S||(f.as="script"),f.crossOrigin="",f.href=c,r&&f.setAttribute("nonce",r),document.head.appendChild(f),S)return new Promise((y,T)=>{f.addEventListener("load",y),f.addEventListener("error",()=>T(new Error(`Unable to preload CSS for ${c}`)))})}))}function a(p){const r=new Event("vite:preloadError",{cancelable:!0});if(r.payload=p,window.dispatchEvent(r),!r.defaultPrevented)throw p}return s.then(p=>{for(const r of p||[])r.status==="rejected"&&a(r.reason);return n().catch(a)})};function oe(){return oe=Object.assign?Object.assign.bind():function(u){for(var n=1;n<arguments.length;n++){var i=arguments[n];for(var e in i)({}).hasOwnProperty.call(i,e)&&(u[e]=i[e])}return u},oe.apply(null,arguments)}const rt=parseInt(Mt.replace(/\D+/g,"")),lt=rt>=125?"uv1":"uv2";var Wt=Object.defineProperty,Yt=(u,n,i)=>n in u?Wt(u,n,{enumerable:!0,configurable:!0,writable:!0,value:i}):u[n]=i,Vt=(u,n,i)=>(Yt(u,n+"",i),i);class Gt{constructor(){Vt(this,"_listeners")}addEventListener(n,i){this._listeners===void 0&&(this._listeners={});const e=this._listeners;e[n]===void 0&&(e[n]=[]),e[n].indexOf(i)===-1&&e[n].push(i)}hasEventListener(n,i){if(this._listeners===void 0)return!1;const e=this._listeners;return e[n]!==void 0&&e[n].indexOf(i)!==-1}removeEventListener(n,i){if(this._listeners===void 0)return;const s=this._listeners[n];if(s!==void 0){const a=s.indexOf(i);a!==-1&&s.splice(a,1)}}dispatchEvent(n){if(this._listeners===void 0)return;const e=this._listeners[n.type];if(e!==void 0){n.target=this;const s=e.slice(0);for(let a=0,p=s.length;a<p;a++)s[a].call(this,n);n.target=null}}}var Zt=Object.defineProperty,Xt=(u,n,i)=>n in u?Zt(u,n,{enumerable:!0,configurable:!0,writable:!0,value:i}):u[n]=i,l=(u,n,i)=>(Xt(u,typeof n!="symbol"?n+"":n,i),i);const le=new Tt,Je=new Dt,Kt=Math.cos(70*(Math.PI/180)),et=(u,n)=>(u%n+n)%n;let qt=class extends Gt{constructor(n,i){super(),l(this,"object"),l(this,"domElement"),l(this,"enabled",!0),l(this,"target",new x),l(this,"minDistance",0),l(this,"maxDistance",1/0),l(this,"minZoom",0),l(this,"maxZoom",1/0),l(this,"minPolarAngle",0),l(this,"maxPolarAngle",Math.PI),l(this,"minAzimuthAngle",-1/0),l(this,"maxAzimuthAngle",1/0),l(this,"enableDamping",!1),l(this,"dampingFactor",.05),l(this,"enableZoom",!0),l(this,"zoomSpeed",1),l(this,"enableRotate",!0),l(this,"rotateSpeed",1),l(this,"enablePan",!0),l(this,"panSpeed",1),l(this,"screenSpacePanning",!0),l(this,"keyPanSpeed",7),l(this,"zoomToCursor",!1),l(this,"autoRotate",!1),l(this,"autoRotateSpeed",2),l(this,"reverseOrbit",!1),l(this,"reverseHorizontalOrbit",!1),l(this,"reverseVerticalOrbit",!1),l(this,"keys",{LEFT:"ArrowLeft",UP:"ArrowUp",RIGHT:"ArrowRight",BOTTOM:"ArrowDown"}),l(this,"mouseButtons",{LEFT:K.ROTATE,MIDDLE:K.DOLLY,RIGHT:K.PAN}),l(this,"touches",{ONE:q.ROTATE,TWO:q.DOLLY_PAN}),l(this,"target0"),l(this,"position0"),l(this,"zoom0"),l(this,"_domElementKeyEvents",null),l(this,"getPolarAngle"),l(this,"getAzimuthalAngle"),l(this,"setPolarAngle"),l(this,"setAzimuthalAngle"),l(this,"getDistance"),l(this,"getZoomScale"),l(this,"listenToKeyEvents"),l(this,"stopListenToKeyEvents"),l(this,"saveState"),l(this,"reset"),l(this,"update"),l(this,"connect"),l(this,"dispose"),l(this,"dollyIn"),l(this,"dollyOut"),l(this,"getScale"),l(this,"setScale"),this.object=n,this.domElement=i,this.target0=this.target.clone(),this.position0=this.object.position.clone(),this.zoom0=this.object.zoom,this.getPolarAngle=()=>h.phi,this.getAzimuthalAngle=()=>h.theta,this.setPolarAngle=t=>{let o=et(t,2*Math.PI),d=h.phi;d<0&&(d+=2*Math.PI),o<0&&(o+=2*Math.PI);let g=Math.abs(o-d);2*Math.PI-g<g&&(o<d?o+=2*Math.PI:d+=2*Math.PI),f.phi=o-d,e.update()},this.setAzimuthalAngle=t=>{let o=et(t,2*Math.PI),d=h.theta;d<0&&(d+=2*Math.PI),o<0&&(o+=2*Math.PI);let g=Math.abs(o-d);2*Math.PI-g<g&&(o<d?o+=2*Math.PI:d+=2*Math.PI),f.theta=o-d,e.update()},this.getDistance=()=>e.object.position.distanceTo(e.target),this.listenToKeyEvents=t=>{t.addEventListener("keydown",be),this._domElementKeyEvents=t},this.stopListenToKeyEvents=()=>{this._domElementKeyEvents.removeEventListener("keydown",be),this._domElementKeyEvents=null},this.saveState=()=>{e.target0.copy(e.target),e.position0.copy(e.object.position),e.zoom0=e.object.zoom},this.reset=()=>{e.target.copy(e.target0),e.object.position.copy(e.position0),e.object.zoom=e.zoom0,e.object.updateProjectionMatrix(),e.dispatchEvent(s),e.update(),c=r.NONE},this.update=(()=>{const t=new x,o=new x(0,1,0),d=new Ge().setFromUnitVectors(n.up,o),g=d.clone().invert(),_=new x,k=new Ge,V=2*Math.PI;return function(){const Ye=e.object.position;d.setFromUnitVectors(n.up,o),g.copy(d).invert(),t.copy(Ye).sub(e.target),t.applyQuaternion(d),h.setFromVector3(t),e.autoRotate&&c===r.NONE&&fe(ut()),e.enableDamping?(h.theta+=f.theta*e.dampingFactor,h.phi+=f.phi*e.dampingFactor):(h.theta+=f.theta,h.phi+=f.phi);let F=e.minAzimuthAngle,W=e.maxAzimuthAngle;isFinite(F)&&isFinite(W)&&(F<-Math.PI?F+=V:F>Math.PI&&(F-=V),W<-Math.PI?W+=V:W>Math.PI&&(W-=V),F<=W?h.theta=Math.max(F,Math.min(W,h.theta)):h.theta=h.theta>(F+W)/2?Math.max(F,h.theta):Math.min(W,h.theta)),h.phi=Math.max(e.minPolarAngle,Math.min(e.maxPolarAngle,h.phi)),h.makeSafe(),e.enableDamping===!0?e.target.addScaledVector(T,e.dampingFactor):e.target.add(T),e.zoomToCursor&&R||e.object.isOrthographicCamera?h.radius=me(h.radius):h.radius=me(h.radius*y),t.setFromSpherical(h),t.applyQuaternion(g),Ye.copy(e.target).add(t),e.object.matrixAutoUpdate||e.object.updateMatrix(),e.object.lookAt(e.target),e.enableDamping===!0?(f.theta*=1-e.dampingFactor,f.phi*=1-e.dampingFactor,T.multiplyScalar(1-e.dampingFactor)):(f.set(0,0,0),T.set(0,0,0));let te=!1;if(e.zoomToCursor&&R){let ne=null;if(e.object instanceof Ee&&e.object.isPerspectiveCamera){const ie=t.length();ne=me(ie*y);const re=ie-ne;e.object.position.addScaledVector(J,re),e.object.updateMatrixWorld()}else if(e.object.isOrthographicCamera){const ie=new x(I.x,I.y,0);ie.unproject(e.object),e.object.zoom=Math.max(e.minZoom,Math.min(e.maxZoom,e.object.zoom/y)),e.object.updateProjectionMatrix(),te=!0;const re=new x(I.x,I.y,0);re.unproject(e.object),e.object.position.sub(re).add(ie),e.object.updateMatrixWorld(),ne=t.length()}else console.warn("WARNING: OrbitControls.js encountered an unknown camera type - zoom to cursor disabled."),e.zoomToCursor=!1;ne!==null&&(e.screenSpacePanning?e.target.set(0,0,-1).transformDirection(e.object.matrix).multiplyScalar(ne).add(e.object.position):(le.origin.copy(e.object.position),le.direction.set(0,0,-1).transformDirection(e.object.matrix),Math.abs(e.object.up.dot(le.direction))<Kt?n.lookAt(e.target):(Je.setFromNormalAndCoplanarPoint(e.object.up,e.target),le.intersectPlane(Je,e.target))))}else e.object instanceof ye&&e.object.isOrthographicCamera&&(te=y!==1,te&&(e.object.zoom=Math.max(e.minZoom,Math.min(e.maxZoom,e.object.zoom/y)),e.object.updateProjectionMatrix()));return y=1,R=!1,te||_.distanceToSquared(e.object.position)>S||8*(1-k.dot(e.object.quaternion))>S?(e.dispatchEvent(s),_.copy(e.object.position),k.copy(e.object.quaternion),te=!1,!0):!1}})(),this.connect=t=>{e.domElement=t,e.domElement.style.touchAction="none",e.domElement.addEventListener("contextmenu",Fe),e.domElement.addEventListener("pointerdown",He),e.domElement.addEventListener("pointercancel",ee),e.domElement.addEventListener("wheel",ke)},this.dispose=()=>{var t,o,d,g,_,k;e.domElement&&(e.domElement.style.touchAction="auto"),(t=e.domElement)==null||t.removeEventListener("contextmenu",Fe),(o=e.domElement)==null||o.removeEventListener("pointerdown",He),(d=e.domElement)==null||d.removeEventListener("pointercancel",ee),(g=e.domElement)==null||g.removeEventListener("wheel",ke),(_=e.domElement)==null||_.ownerDocument.removeEventListener("pointermove",ge),(k=e.domElement)==null||k.ownerDocument.removeEventListener("pointerup",ee),e._domElementKeyEvents!==null&&e._domElementKeyEvents.removeEventListener("keydown",be)};const e=this,s={type:"change"},a={type:"start"},p={type:"end"},r={NONE:-1,ROTATE:0,DOLLY:1,PAN:2,TOUCH_ROTATE:3,TOUCH_PAN:4,TOUCH_DOLLY_PAN:5,TOUCH_DOLLY_ROTATE:6};let c=r.NONE;const S=1e-6,h=new Ve,f=new Ve;let y=1;const T=new x,A=new z,D=new z,j=new z,L=new z,C=new z,m=new z,E=new z,w=new z,v=new z,J=new x,I=new z;let R=!1;const b=[],se={};function ut(){return 2*Math.PI/60/60*e.autoRotateSpeed}function G(){return Math.pow(.95,e.zoomSpeed)}function fe(t){e.reverseOrbit||e.reverseHorizontalOrbit?f.theta+=t:f.theta-=t}function Pe(t){e.reverseOrbit||e.reverseVerticalOrbit?f.phi+=t:f.phi-=t}const Me=(()=>{const t=new x;return function(d,g){t.setFromMatrixColumn(g,0),t.multiplyScalar(-d),T.add(t)}})(),Te=(()=>{const t=new x;return function(d,g){e.screenSpacePanning===!0?t.setFromMatrixColumn(g,1):(t.setFromMatrixColumn(g,0),t.crossVectors(e.object.up,t)),t.multiplyScalar(d),T.add(t)}})(),X=(()=>{const t=new x;return function(d,g){const _=e.domElement;if(_&&e.object instanceof Ee&&e.object.isPerspectiveCamera){const k=e.object.position;t.copy(k).sub(e.target);let V=t.length();V*=Math.tan(e.object.fov/2*Math.PI/180),Me(2*d*V/_.clientHeight,e.object.matrix),Te(2*g*V/_.clientHeight,e.object.matrix)}else _&&e.object instanceof ye&&e.object.isOrthographicCamera?(Me(d*(e.object.right-e.object.left)/e.object.zoom/_.clientWidth,e.object.matrix),Te(g*(e.object.top-e.object.bottom)/e.object.zoom/_.clientHeight,e.object.matrix)):(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - pan disabled."),e.enablePan=!1)}})();function pe(t){e.object instanceof Ee&&e.object.isPerspectiveCamera||e.object instanceof ye&&e.object.isOrthographicCamera?y=t:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),e.enableZoom=!1)}function ae(t){pe(y/t)}function he(t){pe(y*t)}function De(t){if(!e.zoomToCursor||!e.domElement)return;R=!0;const o=e.domElement.getBoundingClientRect(),d=t.clientX-o.left,g=t.clientY-o.top,_=o.width,k=o.height;I.x=d/_*2-1,I.y=-(g/k)*2+1,J.set(I.x,I.y,1).unproject(e.object).sub(e.object.position).normalize()}function me(t){return Math.max(e.minDistance,Math.min(e.maxDistance,t))}function je(t){A.set(t.clientX,t.clientY)}function ft(t){De(t),E.set(t.clientX,t.clientY)}function Ue(t){L.set(t.clientX,t.clientY)}function pt(t){D.set(t.clientX,t.clientY),j.subVectors(D,A).multiplyScalar(e.rotateSpeed);const o=e.domElement;o&&(fe(2*Math.PI*j.x/o.clientHeight),Pe(2*Math.PI*j.y/o.clientHeight)),A.copy(D),e.update()}function ht(t){w.set(t.clientX,t.clientY),v.subVectors(w,E),v.y>0?ae(G()):v.y<0&&he(G()),E.copy(w),e.update()}function mt(t){C.set(t.clientX,t.clientY),m.subVectors(C,L).multiplyScalar(e.panSpeed),X(m.x,m.y),L.copy(C),e.update()}function gt(t){De(t),t.deltaY<0?he(G()):t.deltaY>0&&ae(G()),e.update()}function bt(t){let o=!1;switch(t.code){case e.keys.UP:X(0,e.keyPanSpeed),o=!0;break;case e.keys.BOTTOM:X(0,-e.keyPanSpeed),o=!0;break;case e.keys.LEFT:X(e.keyPanSpeed,0),o=!0;break;case e.keys.RIGHT:X(-e.keyPanSpeed,0),o=!0;break}o&&(t.preventDefault(),e.update())}function Ce(){if(b.length==1)A.set(b[0].pageX,b[0].pageY);else{const t=.5*(b[0].pageX+b[1].pageX),o=.5*(b[0].pageY+b[1].pageY);A.set(t,o)}}function ze(){if(b.length==1)L.set(b[0].pageX,b[0].pageY);else{const t=.5*(b[0].pageX+b[1].pageX),o=.5*(b[0].pageY+b[1].pageY);L.set(t,o)}}function Ie(){const t=b[0].pageX-b[1].pageX,o=b[0].pageY-b[1].pageY,d=Math.sqrt(t*t+o*o);E.set(0,d)}function vt(){e.enableZoom&&Ie(),e.enablePan&&ze()}function yt(){e.enableZoom&&Ie(),e.enableRotate&&Ce()}function Re(t){if(b.length==1)D.set(t.pageX,t.pageY);else{const d=ve(t),g=.5*(t.pageX+d.x),_=.5*(t.pageY+d.y);D.set(g,_)}j.subVectors(D,A).multiplyScalar(e.rotateSpeed);const o=e.domElement;o&&(fe(2*Math.PI*j.x/o.clientHeight),Pe(2*Math.PI*j.y/o.clientHeight)),A.copy(D)}function Ne(t){if(b.length==1)C.set(t.pageX,t.pageY);else{const o=ve(t),d=.5*(t.pageX+o.x),g=.5*(t.pageY+o.y);C.set(d,g)}m.subVectors(C,L).multiplyScalar(e.panSpeed),X(m.x,m.y),L.copy(C)}function Be(t){const o=ve(t),d=t.pageX-o.x,g=t.pageY-o.y,_=Math.sqrt(d*d+g*g);w.set(0,_),v.set(0,Math.pow(w.y/E.y,e.zoomSpeed)),ae(v.y),E.copy(w)}function Et(t){e.enableZoom&&Be(t),e.enablePan&&Ne(t)}function wt(t){e.enableZoom&&Be(t),e.enableRotate&&Re(t)}function He(t){var o,d;e.enabled!==!1&&(b.length===0&&((o=e.domElement)==null||o.ownerDocument.addEventListener("pointermove",ge),(d=e.domElement)==null||d.ownerDocument.addEventListener("pointerup",ee)),Lt(t),t.pointerType==="touch"?_t(t):St(t))}function ge(t){e.enabled!==!1&&(t.pointerType==="touch"?At(t):xt(t))}function ee(t){var o,d,g;Ot(t),b.length===0&&((o=e.domElement)==null||o.releasePointerCapture(t.pointerId),(d=e.domElement)==null||d.ownerDocument.removeEventListener("pointermove",ge),(g=e.domElement)==null||g.ownerDocument.removeEventListener("pointerup",ee)),e.dispatchEvent(p),c=r.NONE}function St(t){let o;switch(t.button){case 0:o=e.mouseButtons.LEFT;break;case 1:o=e.mouseButtons.MIDDLE;break;case 2:o=e.mouseButtons.RIGHT;break;default:o=-1}switch(o){case K.DOLLY:if(e.enableZoom===!1)return;ft(t),c=r.DOLLY;break;case K.ROTATE:if(t.ctrlKey||t.metaKey||t.shiftKey){if(e.enablePan===!1)return;Ue(t),c=r.PAN}else{if(e.enableRotate===!1)return;je(t),c=r.ROTATE}break;case K.PAN:if(t.ctrlKey||t.metaKey||t.shiftKey){if(e.enableRotate===!1)return;je(t),c=r.ROTATE}else{if(e.enablePan===!1)return;Ue(t),c=r.PAN}break;default:c=r.NONE}c!==r.NONE&&e.dispatchEvent(a)}function xt(t){if(e.enabled!==!1)switch(c){case r.ROTATE:if(e.enableRotate===!1)return;pt(t);break;case r.DOLLY:if(e.enableZoom===!1)return;ht(t);break;case r.PAN:if(e.enablePan===!1)return;mt(t);break}}function ke(t){e.enabled===!1||e.enableZoom===!1||c!==r.NONE&&c!==r.ROTATE||(t.preventDefault(),e.dispatchEvent(a),gt(t),e.dispatchEvent(p))}function be(t){e.enabled===!1||e.enablePan===!1||bt(t)}function _t(t){switch(We(t),b.length){case 1:switch(e.touches.ONE){case q.ROTATE:if(e.enableRotate===!1)return;Ce(),c=r.TOUCH_ROTATE;break;case q.PAN:if(e.enablePan===!1)return;ze(),c=r.TOUCH_PAN;break;default:c=r.NONE}break;case 2:switch(e.touches.TWO){case q.DOLLY_PAN:if(e.enableZoom===!1&&e.enablePan===!1)return;vt(),c=r.TOUCH_DOLLY_PAN;break;case q.DOLLY_ROTATE:if(e.enableZoom===!1&&e.enableRotate===!1)return;yt(),c=r.TOUCH_DOLLY_ROTATE;break;default:c=r.NONE}break;default:c=r.NONE}c!==r.NONE&&e.dispatchEvent(a)}function At(t){switch(We(t),c){case r.TOUCH_ROTATE:if(e.enableRotate===!1)return;Re(t),e.update();break;case r.TOUCH_PAN:if(e.enablePan===!1)return;Ne(t),e.update();break;case r.TOUCH_DOLLY_PAN:if(e.enableZoom===!1&&e.enablePan===!1)return;Et(t),e.update();break;case r.TOUCH_DOLLY_ROTATE:if(e.enableZoom===!1&&e.enableRotate===!1)return;wt(t),e.update();break;default:c=r.NONE}}function Fe(t){e.enabled!==!1&&t.preventDefault()}function Lt(t){b.push(t)}function Ot(t){delete se[t.pointerId];for(let o=0;o<b.length;o++)if(b[o].pointerId==t.pointerId){b.splice(o,1);return}}function We(t){let o=se[t.pointerId];o===void 0&&(o=new z,se[t.pointerId]=o),o.set(t.pageX,t.pageY)}function ve(t){const o=t.pointerId===b[0].pointerId?b[1]:b[0];return se[o.pointerId]}this.dollyIn=(t=G())=>{he(t),e.update()},this.dollyOut=(t=G())=>{ae(t),e.update()},this.getScale=()=>y,this.setScale=t=>{pe(t),e.update()},this.getZoomScale=()=>G(),i!==void 0&&this.connect(i),this.update()}};const tt=new Ae,ce=new x;class Le extends jt{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type="LineSegmentsGeometry";const n=[-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],i=[-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],e=[0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5];this.setIndex(e),this.setAttribute("position",new Ze(n,3)),this.setAttribute("uv",new Ze(i,2))}applyMatrix4(n){const i=this.attributes.instanceStart,e=this.attributes.instanceEnd;return i!==void 0&&(i.applyMatrix4(n),e.applyMatrix4(n),i.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(n){let i;n instanceof Float32Array?i=n:Array.isArray(n)&&(i=new Float32Array(n));const e=new _e(i,6,1);return this.setAttribute("instanceStart",new $(e,3,0)),this.setAttribute("instanceEnd",new $(e,3,3)),this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(n,i=3){let e;n instanceof Float32Array?e=n:Array.isArray(n)&&(e=new Float32Array(n));const s=new _e(e,i*2,1);return this.setAttribute("instanceColorStart",new $(s,i,0)),this.setAttribute("instanceColorEnd",new $(s,i,i)),this}fromWireframeGeometry(n){return this.setPositions(n.attributes.position.array),this}fromEdgesGeometry(n){return this.setPositions(n.attributes.position.array),this}fromMesh(n){return this.fromWireframeGeometry(new Ut(n.geometry)),this}fromLineSegments(n){const i=n.geometry;return this.setPositions(i.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new Ae);const n=this.attributes.instanceStart,i=this.attributes.instanceEnd;n!==void 0&&i!==void 0&&(this.boundingBox.setFromBufferAttribute(n),tt.setFromBufferAttribute(i),this.boundingBox.union(tt))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new at),this.boundingBox===null&&this.computeBoundingBox();const n=this.attributes.instanceStart,i=this.attributes.instanceEnd;if(n!==void 0&&i!==void 0){const e=this.boundingSphere.center;this.boundingBox.getCenter(e);let s=0;for(let a=0,p=n.count;a<p;a++)ce.fromBufferAttribute(n,a),s=Math.max(s,e.distanceToSquared(ce)),ce.fromBufferAttribute(i,a),s=Math.max(s,e.distanceToSquared(ce));this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&console.error("THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.",this)}}toJSON(){}applyMatrix(n){return console.warn("THREE.LineSegmentsGeometry: applyMatrix() has been renamed to applyMatrix4()."),this.applyMatrix4(n)}}class ct extends Le{constructor(){super(),this.isLineGeometry=!0,this.type="LineGeometry"}setPositions(n){const i=n.length-3,e=new Float32Array(2*i);for(let s=0;s<i;s+=3)e[2*s]=n[s],e[2*s+1]=n[s+1],e[2*s+2]=n[s+2],e[2*s+3]=n[s+3],e[2*s+4]=n[s+4],e[2*s+5]=n[s+5];return super.setPositions(e),this}setColors(n,i=3){const e=n.length-i,s=new Float32Array(2*e);if(i===3)for(let a=0;a<e;a+=i)s[2*a]=n[a],s[2*a+1]=n[a+1],s[2*a+2]=n[a+2],s[2*a+3]=n[a+3],s[2*a+4]=n[a+4],s[2*a+5]=n[a+5];else for(let a=0;a<e;a+=i)s[2*a]=n[a],s[2*a+1]=n[a+1],s[2*a+2]=n[a+2],s[2*a+3]=n[a+3],s[2*a+4]=n[a+4],s[2*a+5]=n[a+5],s[2*a+6]=n[a+6],s[2*a+7]=n[a+7];return super.setColors(s,i),this}fromLine(n){const i=n.geometry;return this.setPositions(i.attributes.position.array),this}}class Oe extends Ct{constructor(n){super({type:"LineMaterial",uniforms:Xe.clone(Xe.merge([Ke.common,Ke.fog,{worldUnits:{value:1},linewidth:{value:1},resolution:{value:new z(1,1)},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}}])),vertexShader:`
				#include <common>
				#include <fog_pars_vertex>
				#include <logdepthbuf_pars_vertex>
				#include <clipping_planes_pars_vertex>

				uniform float linewidth;
				uniform vec2 resolution;

				attribute vec3 instanceStart;
				attribute vec3 instanceEnd;

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
						attribute vec4 instanceColorStart;
						attribute vec4 instanceColorEnd;
					#else
						varying vec3 vLineColor;
						attribute vec3 instanceColorStart;
						attribute vec3 instanceColorEnd;
					#endif
				#endif

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#ifdef USE_DASH

					uniform float dashScale;
					attribute float instanceDistanceStart;
					attribute float instanceDistanceEnd;
					varying float vLineDistance;

				#endif

				void trimSegment( const in vec4 start, inout vec4 end ) {

					// trim end segment so it terminates between the camera plane and the near plane

					// conservative estimate of the near plane
					float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
					float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column
					float nearEstimate = - 0.5 * b / a;

					float alpha = ( nearEstimate - start.z ) / ( end.z - start.z );

					end.xyz = mix( start.xyz, end.xyz, alpha );

				}

				void main() {

					#ifdef USE_COLOR

						vLineColor = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

					#endif

					#ifdef USE_DASH

						vLineDistance = ( position.y < 0.5 ) ? dashScale * instanceDistanceStart : dashScale * instanceDistanceEnd;
						vUv = uv;

					#endif

					float aspect = resolution.x / resolution.y;

					// camera space
					vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
					vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

					#ifdef WORLD_UNITS

						worldStart = start.xyz;
						worldEnd = end.xyz;

					#else

						vUv = uv;

					#endif

					// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
					// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
					// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
					// perhaps there is a more elegant solution -- WestLangley

					bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

					if ( perspective ) {

						if ( start.z < 0.0 && end.z >= 0.0 ) {

							trimSegment( start, end );

						} else if ( end.z < 0.0 && start.z >= 0.0 ) {

							trimSegment( end, start );

						}

					}

					// clip space
					vec4 clipStart = projectionMatrix * start;
					vec4 clipEnd = projectionMatrix * end;

					// ndc space
					vec3 ndcStart = clipStart.xyz / clipStart.w;
					vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

					// direction
					vec2 dir = ndcEnd.xy - ndcStart.xy;

					// account for clip-space aspect ratio
					dir.x *= aspect;
					dir = normalize( dir );

					#ifdef WORLD_UNITS

						// get the offset direction as perpendicular to the view vector
						vec3 worldDir = normalize( end.xyz - start.xyz );
						vec3 offset;
						if ( position.y < 0.5 ) {

							offset = normalize( cross( start.xyz, worldDir ) );

						} else {

							offset = normalize( cross( end.xyz, worldDir ) );

						}

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						float forwardOffset = dot( worldDir, vec3( 0.0, 0.0, 1.0 ) );

						// don't extend the line if we're rendering dashes because we
						// won't be rendering the endcaps
						#ifndef USE_DASH

							// extend the line bounds to encompass  endcaps
							start.xyz += - worldDir * linewidth * 0.5;
							end.xyz += worldDir * linewidth * 0.5;

							// shift the position of the quad so it hugs the forward edge of the line
							offset.xy -= dir * forwardOffset;
							offset.z += 0.5;

						#endif

						// endcaps
						if ( position.y > 1.0 || position.y < 0.0 ) {

							offset.xy += dir * 2.0 * forwardOffset;

						}

						// adjust for linewidth
						offset *= linewidth * 0.5;

						// set the world position
						worldPos = ( position.y < 0.5 ) ? start : end;
						worldPos.xyz += offset;

						// project the worldpos
						vec4 clip = projectionMatrix * worldPos;

						// shift the depth of the projected points so the line
						// segments overlap neatly
						vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
						clip.z = clipPose.z * clip.w;

					#else

						vec2 offset = vec2( dir.y, - dir.x );
						// undo aspect ratio adjustment
						dir.x /= aspect;
						offset.x /= aspect;

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						// endcaps
						if ( position.y < 0.0 ) {

							offset += - dir;

						} else if ( position.y > 1.0 ) {

							offset += dir;

						}

						// adjust for linewidth
						offset *= linewidth;

						// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
						offset /= resolution.y;

						// select end
						vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

						// back to clip space
						offset *= clip.w;

						clip.xy += offset;

					#endif

					gl_Position = clip;

					vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

					#include <logdepthbuf_vertex>
					#include <clipping_planes_vertex>
					#include <fog_vertex>

				}
			`,fragmentShader:`
				uniform vec3 diffuse;
				uniform float opacity;
				uniform float linewidth;

				#ifdef USE_DASH

					uniform float dashOffset;
					uniform float dashSize;
					uniform float gapSize;

				#endif

				varying float vLineDistance;

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#include <common>
				#include <fog_pars_fragment>
				#include <logdepthbuf_pars_fragment>
				#include <clipping_planes_pars_fragment>

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
					#else
						varying vec3 vLineColor;
					#endif
				#endif

				vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

					float mua;
					float mub;

					vec3 p13 = p1 - p3;
					vec3 p43 = p4 - p3;

					vec3 p21 = p2 - p1;

					float d1343 = dot( p13, p43 );
					float d4321 = dot( p43, p21 );
					float d1321 = dot( p13, p21 );
					float d4343 = dot( p43, p43 );
					float d2121 = dot( p21, p21 );

					float denom = d2121 * d4343 - d4321 * d4321;

					float numer = d1343 * d4321 - d1321 * d4343;

					mua = numer / denom;
					mua = clamp( mua, 0.0, 1.0 );
					mub = ( d1343 + d4321 * ( mua ) ) / d4343;
					mub = clamp( mub, 0.0, 1.0 );

					return vec2( mua, mub );

				}

				void main() {

					#include <clipping_planes_fragment>

					#ifdef USE_DASH

						if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

						if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

					#endif

					float alpha = opacity;

					#ifdef WORLD_UNITS

						// Find the closest points on the view ray and the line segment
						vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
						vec3 lineDir = worldEnd - worldStart;
						vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

						vec3 p1 = worldStart + lineDir * params.x;
						vec3 p2 = rayEnd * params.y;
						vec3 delta = p1 - p2;
						float len = length( delta );
						float norm = len / linewidth;

						#ifndef USE_DASH

							#ifdef USE_ALPHA_TO_COVERAGE

								float dnorm = fwidth( norm );
								alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

							#else

								if ( norm > 0.5 ) {

									discard;

								}

							#endif

						#endif

					#else

						#ifdef USE_ALPHA_TO_COVERAGE

							// artifacts appear on some hardware if a derivative is taken within a conditional
							float a = vUv.x;
							float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
							float len2 = a * a + b * b;
							float dlen = fwidth( len2 );

							if ( abs( vUv.y ) > 1.0 ) {

								alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

							}

						#else

							if ( abs( vUv.y ) > 1.0 ) {

								float a = vUv.x;
								float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
								float len2 = a * a + b * b;

								if ( len2 > 1.0 ) discard;

							}

						#endif

					#endif

					vec4 diffuseColor = vec4( diffuse, alpha );
					#ifdef USE_COLOR
						#ifdef USE_LINE_COLOR_ALPHA
							diffuseColor *= vLineColor;
						#else
							diffuseColor.rgb *= vLineColor;
						#endif
					#endif

					#include <logdepthbuf_fragment>

					gl_FragColor = diffuseColor;

					#include <tonemapping_fragment>
					#include <${rt>=154?"colorspace_fragment":"encodings_fragment"}>
					#include <fog_fragment>
					#include <premultiplied_alpha_fragment>

				}
			`,clipping:!0}),this.isLineMaterial=!0,this.onBeforeCompile=function(){this.transparent?this.defines.USE_LINE_COLOR_ALPHA="1":delete this.defines.USE_LINE_COLOR_ALPHA},Object.defineProperties(this,{color:{enumerable:!0,get:function(){return this.uniforms.diffuse.value},set:function(i){this.uniforms.diffuse.value=i}},worldUnits:{enumerable:!0,get:function(){return"WORLD_UNITS"in this.defines},set:function(i){i===!0?this.defines.WORLD_UNITS="":delete this.defines.WORLD_UNITS}},linewidth:{enumerable:!0,get:function(){return this.uniforms.linewidth.value},set:function(i){this.uniforms.linewidth.value=i}},dashed:{enumerable:!0,get:function(){return"USE_DASH"in this.defines},set(i){!!i!="USE_DASH"in this.defines&&(this.needsUpdate=!0),i===!0?this.defines.USE_DASH="":delete this.defines.USE_DASH}},dashScale:{enumerable:!0,get:function(){return this.uniforms.dashScale.value},set:function(i){this.uniforms.dashScale.value=i}},dashSize:{enumerable:!0,get:function(){return this.uniforms.dashSize.value},set:function(i){this.uniforms.dashSize.value=i}},dashOffset:{enumerable:!0,get:function(){return this.uniforms.dashOffset.value},set:function(i){this.uniforms.dashOffset.value=i}},gapSize:{enumerable:!0,get:function(){return this.uniforms.gapSize.value},set:function(i){this.uniforms.gapSize.value=i}},opacity:{enumerable:!0,get:function(){return this.uniforms.opacity.value},set:function(i){this.uniforms.opacity.value=i}},resolution:{enumerable:!0,get:function(){return this.uniforms.resolution.value},set:function(i){this.uniforms.resolution.value.copy(i)}},alphaToCoverage:{enumerable:!0,get:function(){return"USE_ALPHA_TO_COVERAGE"in this.defines},set:function(i){!!i!="USE_ALPHA_TO_COVERAGE"in this.defines&&(this.needsUpdate=!0),i===!0?(this.defines.USE_ALPHA_TO_COVERAGE="",this.extensions.derivatives=!0):(delete this.defines.USE_ALPHA_TO_COVERAGE,this.extensions.derivatives=!1)}}}),this.setValues(n)}}const we=new Q,nt=new x,it=new x,O=new Q,P=new Q,N=new Q,Se=new x,xe=new Rt,M=new It,ot=new x,de=new Ae,ue=new at,B=new Q;let H,Z;function st(u,n,i){return B.set(0,0,-n,1).applyMatrix4(u.projectionMatrix),B.multiplyScalar(1/B.w),B.x=Z/i.width,B.y=Z/i.height,B.applyMatrix4(u.projectionMatrixInverse),B.multiplyScalar(1/B.w),Math.abs(Math.max(B.x,B.y))}function $t(u,n){const i=u.matrixWorld,e=u.geometry,s=e.attributes.instanceStart,a=e.attributes.instanceEnd,p=Math.min(e.instanceCount,s.count);for(let r=0,c=p;r<c;r++){M.start.fromBufferAttribute(s,r),M.end.fromBufferAttribute(a,r),M.applyMatrix4(i);const S=new x,h=new x;H.distanceSqToSegment(M.start,M.end,h,S),h.distanceTo(S)<Z*.5&&n.push({point:h,pointOnLine:S,distance:H.origin.distanceTo(h),object:u,face:null,faceIndex:r,uv:null,[lt]:null})}}function Qt(u,n,i){const e=n.projectionMatrix,a=u.material.resolution,p=u.matrixWorld,r=u.geometry,c=r.attributes.instanceStart,S=r.attributes.instanceEnd,h=Math.min(r.instanceCount,c.count),f=-n.near;H.at(1,N),N.w=1,N.applyMatrix4(n.matrixWorldInverse),N.applyMatrix4(e),N.multiplyScalar(1/N.w),N.x*=a.x/2,N.y*=a.y/2,N.z=0,Se.copy(N),xe.multiplyMatrices(n.matrixWorldInverse,p);for(let y=0,T=h;y<T;y++){if(O.fromBufferAttribute(c,y),P.fromBufferAttribute(S,y),O.w=1,P.w=1,O.applyMatrix4(xe),P.applyMatrix4(xe),O.z>f&&P.z>f)continue;if(O.z>f){const m=O.z-P.z,E=(O.z-f)/m;O.lerp(P,E)}else if(P.z>f){const m=P.z-O.z,E=(P.z-f)/m;P.lerp(O,E)}O.applyMatrix4(e),P.applyMatrix4(e),O.multiplyScalar(1/O.w),P.multiplyScalar(1/P.w),O.x*=a.x/2,O.y*=a.y/2,P.x*=a.x/2,P.y*=a.y/2,M.start.copy(O),M.start.z=0,M.end.copy(P),M.end.z=0;const D=M.closestPointToPointParameter(Se,!0);M.at(D,ot);const j=Nt.lerp(O.z,P.z,D),L=j>=-1&&j<=1,C=Se.distanceTo(ot)<Z*.5;if(L&&C){M.start.fromBufferAttribute(c,y),M.end.fromBufferAttribute(S,y),M.start.applyMatrix4(p),M.end.applyMatrix4(p);const m=new x,E=new x;H.distanceSqToSegment(M.start,M.end,E,m),i.push({point:E,pointOnLine:m,distance:H.origin.distanceTo(E),object:u,face:null,faceIndex:y,uv:null,[lt]:null})}}}class dt extends zt{constructor(n=new Le,i=new Oe({color:Math.random()*16777215})){super(n,i),this.isLineSegments2=!0,this.type="LineSegments2"}computeLineDistances(){const n=this.geometry,i=n.attributes.instanceStart,e=n.attributes.instanceEnd,s=new Float32Array(2*i.count);for(let p=0,r=0,c=i.count;p<c;p++,r+=2)nt.fromBufferAttribute(i,p),it.fromBufferAttribute(e,p),s[r]=r===0?0:s[r-1],s[r+1]=s[r]+nt.distanceTo(it);const a=new _e(s,2,1);return n.setAttribute("instanceDistanceStart",new $(a,1,0)),n.setAttribute("instanceDistanceEnd",new $(a,1,1)),this}raycast(n,i){const e=this.material.worldUnits,s=n.camera;s===null&&!e&&console.error('LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.');const a=n.params.Line2!==void 0&&n.params.Line2.threshold||0;H=n.ray;const p=this.matrixWorld,r=this.geometry,c=this.material;Z=c.linewidth+a,r.boundingSphere===null&&r.computeBoundingSphere(),ue.copy(r.boundingSphere).applyMatrix4(p);let S;if(e)S=Z*.5;else{const f=Math.max(s.near,ue.distanceToPoint(H.origin));S=st(s,f,c.resolution)}if(ue.radius+=S,H.intersectsSphere(ue)===!1)return;r.boundingBox===null&&r.computeBoundingBox(),de.copy(r.boundingBox).applyMatrix4(p);let h;if(e)h=Z*.5;else{const f=Math.max(s.near,de.distanceToPoint(H.origin));h=st(s,f,c.resolution)}de.expandByScalar(h),H.intersectsBox(de)!==!1&&(e?$t(this,i):Qt(this,s,i))}onBeforeRender(n){const i=this.material.uniforms;i&&i.resolution&&(n.getViewport(we),this.material.uniforms.resolution.value.set(we.z,we.w))}}class Jt extends dt{constructor(n=new ct,i=new Oe({color:Math.random()*16777215})){super(n,i),this.isLine2=!0,this.type="Line2"}}const rn=U.forwardRef(function({points:n,color:i=16777215,vertexColors:e,linewidth:s,lineWidth:a,segments:p,dashed:r,...c},S){var h,f;const y=Y(L=>L.size),T=U.useMemo(()=>p?new dt:new Jt,[p]),[A]=U.useState(()=>new Oe),D=(e==null||(h=e[0])==null?void 0:h.length)===4?4:3,j=U.useMemo(()=>{const L=p?new Le:new ct,C=n.map(m=>{const E=Array.isArray(m);return m instanceof x||m instanceof Q?[m.x,m.y,m.z]:m instanceof z?[m.x,m.y,0]:E&&m.length===3?[m[0],m[1],m[2]]:E&&m.length===2?[m[0],m[1],0]:m});if(L.setPositions(C.flat()),e){i=16777215;const m=e.map(E=>E instanceof Bt?E.toArray():E);L.setColors(m.flat(),D)}return L},[n,p,e,D]);return U.useLayoutEffect(()=>{T.computeLineDistances()},[n,T]),U.useLayoutEffect(()=>{r?A.defines.USE_DASH="":delete A.defines.USE_DASH,A.needsUpdate=!0},[r,A]),U.useEffect(()=>()=>{j.dispose(),A.dispose()},[j]),U.createElement("primitive",oe({object:T,ref:S},c),U.createElement("primitive",{object:j,attach:"geometry"}),U.createElement("primitive",oe({object:A,attach:"material",color:i,vertexColors:!!e,resolution:[y.width,y.height],linewidth:(f=s??a)!==null&&f!==void 0?f:1,dashed:r,transparent:D===4},c)))}),ln=U.forwardRef(({makeDefault:u,camera:n,regress:i,domElement:e,enableDamping:s=!0,keyEvents:a=!1,onChange:p,onStart:r,onEnd:c,...S},h)=>{const f=Y(v=>v.invalidate),y=Y(v=>v.camera),T=Y(v=>v.gl),A=Y(v=>v.events),D=Y(v=>v.setEvents),j=Y(v=>v.set),L=Y(v=>v.get),C=Y(v=>v.performance),m=n||y,E=e||A.connected||T.domElement,w=U.useMemo(()=>new qt(m),[m]);return Ht(()=>{w.enabled&&w.update()},-1),U.useEffect(()=>(a&&w.connect(a===!0?E:a),w.connect(E),()=>void w.dispose()),[a,E,i,w,f]),U.useEffect(()=>{const v=R=>{f(),i&&C.regress(),p&&p(R)},J=R=>{r&&r(R)},I=R=>{c&&c(R)};return w.addEventListener("change",v),w.addEventListener("start",J),w.addEventListener("end",I),()=>{w.removeEventListener("start",J),w.removeEventListener("end",I),w.removeEventListener("change",v)}},[p,r,c,w,f,D]),U.useEffect(()=>{if(u){const v=L().controls;return j({controls:w}),()=>j({controls:v})}},[u,w]),U.createElement("primitive",oe({ref:h,object:w,enableDamping:s},S))});export{rn as L,ln as O,sn as _,qe as c};
