// Procedural environment — floor, sky dome, time-of-day lighting, props
// Only active in fullwindow/fullscreen modes

// Time-of-day color palettes (hour 0-23 mapped to key hours, lerp between)
const TIME_PALETTE = [
    // [hour, skyTop, skyBottom, sunColor, sunIntensity, ambientIntensity, ambientColor]
    [0,  '#0a0a1a', '#0d1117', '#334477', 0.2, 0.3, '#1a1a3a'],  // midnight
    [5,  '#1a1030', '#2d1b4e', '#553366', 0.3, 0.35, '#2a1a3a'],  // predawn
    [6,  '#4a2040', '#ff8855', '#ffaa66', 0.7, 0.5, '#4a3030'],   // dawn
    [7,  '#5577bb', '#ffcc88', '#ffddaa', 1.0, 0.6, '#555555'],   // sunrise
    [9,  '#4488cc', '#88bbee', '#ffffff', 1.2, 0.7, '#666666'],   // morning
    [12, '#3377cc', '#66aadd', '#ffffff', 1.3, 0.7, '#666666'],   // noon
    [17, '#5577aa', '#ffbb77', '#ffcc88', 1.0, 0.6, '#555544'],   // late afternoon
    [18, '#553355', '#ff7744', '#ff9966', 0.7, 0.5, '#443333'],   // sunset
    [19, '#1a1030', '#443355', '#554466', 0.4, 0.35, '#2a1a3a'],  // dusk
    [21, '#0d0d1a', '#111122', '#334466', 0.2, 0.3, '#1a1a3a'],   // night
];

function lerpColor(hex1, hex2, t) {
    const r1 = parseInt(hex1.slice(1,3), 16), g1 = parseInt(hex1.slice(3,5), 16), b1 = parseInt(hex1.slice(5,7), 16);
    const r2 = parseInt(hex2.slice(1,3), 16), g2 = parseInt(hex2.slice(3,5), 16), b2 = parseInt(hex2.slice(5,7), 16);
    const r = Math.round(r1 + (r2-r1)*t), g = Math.round(g1 + (g2-g1)*t), b = Math.round(b1 + (b2-b1)*t);
    return (r << 16) | (g << 8) | b;
}

function lerp(a, b, t) { return a + (b - a) * t; }

function getTimeOfDay() {
    const now = new Date();
    return now.getHours() + now.getMinutes() / 60;
}

function samplePalette(hour) {
    // Find surrounding keyframes
    let lo = TIME_PALETTE[TIME_PALETTE.length - 1];
    let hi = TIME_PALETTE[0];
    for (let i = 0; i < TIME_PALETTE.length; i++) {
        if (TIME_PALETTE[i][0] <= hour) lo = TIME_PALETTE[i];
        if (TIME_PALETTE[i][0] > hour) { hi = TIME_PALETTE[i]; break; }
        if (i === TIME_PALETTE.length - 1) hi = TIME_PALETTE[0]; // wrap
    }
    const range = hi[0] > lo[0] ? hi[0] - lo[0] : (24 - lo[0] + hi[0]);
    const t = range > 0 ? ((hour - lo[0] + 24) % 24) / range : 0;
    return {
        skyTop:    lerpColor(lo[1], hi[1], t),
        skyBottom: lerpColor(lo[2], hi[2], t),
        sunColor:  lerpColor(lo[3], hi[3], t),
        sunIntensity:     lerp(lo[4], hi[4], t),
        ambientIntensity: lerp(lo[5], hi[5], t),
        ambientColor:     lerpColor(lo[6], hi[6], t),
        sunAngle: (hour / 24) * Math.PI * 2 - Math.PI / 2,  // full arc
    };
}

export function createEnvironment(scene, THREE, renderer) {
    const group = new THREE.Group();
    group.visible = false;
    scene.add(group);

    // --- Enable shadows ---
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // --- Floor ---
    const floorGeo = new THREE.PlaneGeometry(30, 30);
    const floorMat = new THREE.MeshStandardMaterial({
        color: 0x1a1a2a,
        roughness: 0.6,
        metalness: 0.2,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.01;
    floor.receiveShadow = true;
    group.add(floor);

    // Floor grid overlay
    const gridHelper = new THREE.GridHelper(30, 30, 0x2a2a4a, 0x1a1a3a);
    gridHelper.position.y = 0.01;
    gridHelper.material.opacity = 0.3;
    gridHelper.material.transparent = true;
    group.add(gridHelper);

    // --- Sky dome (hemisphere) ---
    const skyGeo = new THREE.SphereGeometry(50, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    const skyMat = new THREE.ShaderMaterial({
        uniforms: {
            topColor:    { value: new THREE.Color(0x0a0a1a) },
            bottomColor: { value: new THREE.Color(0x0d1117) },
        },
        vertexShader: `
            varying vec3 vWorldPos;
            void main() {
                vec4 wp = modelMatrix * vec4(position, 1.0);
                vWorldPos = wp.xyz;
                gl_Position = projectionMatrix * viewMatrix * wp;
            }
        `,
        fragmentShader: `
            uniform vec3 topColor;
            uniform vec3 bottomColor;
            varying vec3 vWorldPos;
            void main() {
                float h = normalize(vWorldPos).y;
                gl_FragColor = vec4(mix(bottomColor, topColor, max(h, 0.0)), 1.0);
            }
        `,
        side: THREE.BackSide,
        depthWrite: false,
    });
    const skyDome = new THREE.Mesh(skyGeo, skyMat);
    group.add(skyDome);

    // --- Stars (particle system) ---
    const starCount = 200;
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.random() * Math.PI * 0.45;  // upper hemisphere only
        const r = 45;
        starPositions[i*3]     = r * Math.sin(phi) * Math.cos(theta);
        starPositions[i*3 + 1] = r * Math.cos(phi);
        starPositions[i*3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.15, transparent: true, opacity: 0.6 });
    const stars = new THREE.Points(starGeo, starMat);
    group.add(stars);

    // --- Sun/moon glow ---
    const sunGeo = new THREE.SphereGeometry(1.5, 16, 16);
    const sunMat = new THREE.MeshBasicMaterial({ color: 0xffcc88, transparent: true, opacity: 0.6 });
    const sunOrb = new THREE.Mesh(sunGeo, sunMat);
    group.add(sunOrb);

    // --- Time-of-day lighting (replaces scene defaults when environment is active) ---
    const envSunLight = new THREE.DirectionalLight(0xffffff, 1.0);
    envSunLight.castShadow = true;
    envSunLight.shadow.mapSize.set(1024, 1024);
    envSunLight.shadow.camera.near = 0.5;
    envSunLight.shadow.camera.far = 30;
    envSunLight.shadow.camera.left = -10;
    envSunLight.shadow.camera.right = 10;
    envSunLight.shadow.camera.top = 10;
    envSunLight.shadow.camera.bottom = -10;
    group.add(envSunLight);

    const envAmbient = new THREE.AmbientLight(0x666666, 0.7);
    group.add(envAmbient);

    // --- PROPS ---
    const props = new THREE.Group();
    group.add(props);

    // Fireplace — back wall area
    const fireplaceBase = new THREE.Mesh(
        new THREE.BoxGeometry(1.2, 0.8, 0.6),
        new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.9 })
    );
    fireplaceBase.position.set(-3, 0.4, -4);
    fireplaceBase.castShadow = true;
    props.add(fireplaceBase);

    const fireplaceMantel = new THREE.Mesh(
        new THREE.BoxGeometry(1.5, 0.08, 0.7),
        new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.8 })
    );
    fireplaceMantel.position.set(-3, 0.84, -4);
    props.add(fireplaceMantel);

    // Fireplace glow light
    const fireLight = new THREE.PointLight(0xff6622, 0.8, 5);
    fireLight.position.set(-3, 0.5, -3.6);
    props.add(fireLight);

    // Fire particles (embers)
    const emberCount = 30;
    const emberPositions = new Float32Array(emberCount * 3);
    for (let i = 0; i < emberCount; i++) {
        emberPositions[i*3]     = -3 + (Math.random() - 0.5) * 0.6;
        emberPositions[i*3 + 1] = 0.3 + Math.random() * 0.5;
        emberPositions[i*3 + 2] = -3.8 + (Math.random() - 0.5) * 0.3;
    }
    const emberGeo = new THREE.BufferGeometry();
    emberGeo.setAttribute('position', new THREE.BufferAttribute(emberPositions, 3));
    const emberMat = new THREE.PointsMaterial({ color: 0xff4400, size: 0.08, transparent: true, opacity: 0.8 });
    const embers = new THREE.Points(emberGeo, emberMat);
    props.add(embers);

    // Couch — right side
    const couchSeat = new THREE.Mesh(
        new THREE.BoxGeometry(2.0, 0.35, 0.8),
        new THREE.MeshStandardMaterial({ color: 0x2a3a5a, roughness: 0.85 })
    );
    couchSeat.position.set(3, 0.25, -2);
    couchSeat.castShadow = true;
    props.add(couchSeat);

    const couchBack = new THREE.Mesh(
        new THREE.BoxGeometry(2.0, 0.5, 0.15),
        new THREE.MeshStandardMaterial({ color: 0x253555, roughness: 0.85 })
    );
    couchBack.position.set(3, 0.55, -2.35);
    couchBack.castShadow = true;
    props.add(couchBack);

    // Couch arm rests
    for (const side of [-1, 1]) {
        const arm = new THREE.Mesh(
            new THREE.BoxGeometry(0.15, 0.4, 0.8),
            new THREE.MeshStandardMaterial({ color: 0x253555, roughness: 0.85 })
        );
        arm.position.set(3 + side * 1.0, 0.4, -2);
        arm.castShadow = true;
        props.add(arm);
    }

    // Minibar + snacks — near couch
    const barTable = new THREE.Mesh(
        new THREE.BoxGeometry(0.8, 0.6, 0.4),
        new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.8 })
    );
    barTable.position.set(4.5, 0.3, -1);
    barTable.castShadow = true;
    props.add(barTable);

    // Bottles on bar (cylinders)
    for (let i = 0; i < 3; i++) {
        const bottle = new THREE.Mesh(
            new THREE.CylinderGeometry(0.04, 0.04, 0.25, 8),
            new THREE.MeshStandardMaterial({
                color: [0x338855, 0x885533, 0x4488aa][i],
                roughness: 0.3, metalness: 0.4
            })
        );
        bottle.position.set(4.3 + i * 0.15, 0.72, -1);
        bottle.castShadow = true;
        props.add(bottle);
    }

    // Bed — far right
    const bedFrame = new THREE.Mesh(
        new THREE.BoxGeometry(1.6, 0.3, 2.2),
        new THREE.MeshStandardMaterial({ color: 0x3a3030, roughness: 0.9 })
    );
    bedFrame.position.set(5.5, 0.15, -4);
    bedFrame.castShadow = true;
    props.add(bedFrame);

    const mattress = new THREE.Mesh(
        new THREE.BoxGeometry(1.4, 0.15, 2.0),
        new THREE.MeshStandardMaterial({ color: 0x4a5577, roughness: 0.95 })
    );
    mattress.position.set(5.5, 0.37, -4);
    props.add(mattress);

    const pillow = new THREE.Mesh(
        new THREE.BoxGeometry(0.5, 0.1, 0.3),
        new THREE.MeshStandardMaterial({ color: 0x6677aa, roughness: 0.95 })
    );
    pillow.position.set(5.5, 0.47, -4.8);
    props.add(pillow);

    // Lake window — back center-left, tall frame with "window" glow
    const windowFrame = new THREE.Mesh(
        new THREE.BoxGeometry(2.5, 2.0, 0.1),
        new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.8 })
    );
    windowFrame.position.set(0, 1.2, -5);
    props.add(windowFrame);

    // Window "glass" — emissive panel showing lake-sky color
    const windowGlass = new THREE.Mesh(
        new THREE.PlaneGeometry(2.2, 1.7),
        new THREE.MeshBasicMaterial({ color: 0x224466, transparent: true, opacity: 0.8 })
    );
    windowGlass.position.set(0, 1.2, -4.94);
    props.add(windowGlass);

    // Window light spill
    const windowLight = new THREE.SpotLight(0x4477aa, 0.5, 8, Math.PI / 4);
    windowLight.position.set(0, 2, -4.5);
    windowLight.target.position.set(0, 0, 0);
    props.add(windowLight);
    props.add(windowLight.target);

    // Chairs in front of window
    for (const xOff of [-0.8, 0.8]) {
        // Seat
        const seat = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 0.05, 0.5),
            new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.85 })
        );
        seat.position.set(xOff, 0.4, -3.8);
        seat.castShadow = true;
        props.add(seat);
        // Back
        const back = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 0.5, 0.05),
            new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.85 })
        );
        back.position.set(xOff, 0.65, -4.02);
        back.castShadow = true;
        props.add(back);
        // Legs
        for (const lx of [-0.2, 0.2]) {
            for (const lz of [-0.2, 0.2]) {
                const leg = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.02, 0.02, 0.4, 6),
                    new THREE.MeshStandardMaterial({ color: 0x3a2a1a })
                );
                leg.position.set(xOff + lx, 0.2, -3.8 + lz);
                props.add(leg);
            }
        }
    }

    // Small table between window chairs
    const sideTable = new THREE.Mesh(
        new THREE.CylinderGeometry(0.25, 0.25, 0.4, 12),
        new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.8 })
    );
    sideTable.position.set(0, 0.2, -3.8);
    sideTable.castShadow = true;
    props.add(sideTable);

    // --- Ember animation state ---
    const _emberBasePositions = new Float32Array(emberPositions);

    // --- Update function (called each frame) ---
    let _lastTimeUpdate = 0;

    function update(delta) {
        if (!group.visible) return;

        // Update time-of-day every 30s
        const now = performance.now();
        if (now - _lastTimeUpdate > 30000 || _lastTimeUpdate === 0) {
            _lastTimeUpdate = now;
            applyTimeOfDay();
        }

        // Animate embers (gentle float upward + flicker)
        const positions = emberGeo.attributes.position.array;
        for (let i = 0; i < emberCount; i++) {
            positions[i*3 + 1] += delta * (0.1 + Math.random() * 0.15);
            positions[i*3]     += (Math.random() - 0.5) * delta * 0.1;
            // Reset if too high
            if (positions[i*3 + 1] > 1.2) {
                positions[i*3]     = _emberBasePositions[i*3] + (Math.random() - 0.5) * 0.3;
                positions[i*3 + 1] = _emberBasePositions[i*3 + 1];
                positions[i*3 + 2] = _emberBasePositions[i*3 + 2];
            }
        }
        emberGeo.attributes.position.needsUpdate = true;

        // Fireplace light flicker
        fireLight.intensity = 0.6 + Math.random() * 0.4;
    }

    function applyTimeOfDay() {
        const hour = getTimeOfDay();
        const p = samplePalette(hour);

        skyMat.uniforms.topColor.value.setHex(p.skyTop);
        skyMat.uniforms.bottomColor.value.setHex(p.skyBottom);

        envSunLight.color.setHex(p.sunColor);
        envSunLight.intensity = p.sunIntensity;

        envAmbient.color.setHex(p.ambientColor);
        envAmbient.intensity = p.ambientIntensity;

        // Sun orb position (arc across sky)
        const sunDist = 35;
        sunOrb.position.set(
            Math.cos(p.sunAngle) * sunDist,
            Math.sin(p.sunAngle) * sunDist * 0.6 + 5,
            -10
        );
        sunOrb.material.color.setHex(p.sunColor);
        sunOrb.material.opacity = Math.max(0, Math.sin(p.sunAngle) * 0.8);
        sunOrb.visible = sunOrb.material.opacity > 0.05;

        // Sun light direction follows orb
        envSunLight.position.copy(sunOrb.position);

        // Stars fade with daylight
        const nightFactor = Math.max(0, 1 - p.sunIntensity / 0.8);
        starMat.opacity = nightFactor * 0.6;
        stars.visible = nightFactor > 0.05;

        // Window glass color shifts with sky
        windowGlass.material.color.setHex(p.skyBottom);

        // Floor color subtle shift
        const floorBrightness = 0.1 + p.ambientIntensity * 0.15;
        floorMat.color.setRGB(floorBrightness, floorBrightness, floorBrightness * 1.2);
    }

    function setVisible(visible) {
        group.visible = visible;
        if (visible) applyTimeOfDay();
    }

    // Enable shadow casting on the avatar model when environment is on
    function enableAvatarShadows(model) {
        model.traverse(child => {
            if (child.isMesh) child.castShadow = true;
        });
    }

    return { update, setVisible, enableAvatarShadows, group };
}
