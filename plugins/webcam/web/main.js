// Webcam capture — listens for capture_webcam tool_start events
// and captures a frame from the user's camera.

import { fetchWithTimeout } from '/static/shared/fetch.js';

let capturing = false;

async function onToolStart(e) {
    const { name } = e.detail;
    if (name !== 'capture_webcam' || capturing) return;

    capturing = true;
    console.log('[Webcam] Tool started — initiating capture');

    try {
        // 1. Get the nonce from the pending capture request
        const pending = await fetchWithTimeout('/api/plugin/webcam/pending');
        if (!pending?.pending || !pending.nonce) {
            console.warn('[Webcam] No pending capture request');
            return;
        }

        // 2. Check secure context (browsers block camera on non-secure origins)
        if (!window.isSecureContext) {
            const msg = `[Webcam] Camera blocked — not a secure context. ` +
                `Use https:// or access via localhost instead of ${location.hostname}`;
            console.error(msg);
            await fetchWithTimeout('/api/plugin/webcam/capture', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nonce: pending.nonce, error: msg })
            });
            return;
        }

        // 3. Request camera access
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
            });
        } catch (err) {
            const msg = `[Webcam] Camera access denied: ${err.message}. ` +
                (err.name === 'NotAllowedError'
                    ? 'Grant camera permission in browser settings.'
                    : 'Check that a camera is connected.');
            console.error(msg);
            await fetchWithTimeout('/api/plugin/webcam/capture', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nonce: pending.nonce, error: msg })
            });
            return;
        }

        // 3. Capture a single frame
        const video = document.createElement('video');
        video.srcObject = stream;
        video.playsInline = true;
        await video.play();

        // Brief delay for camera to stabilize (auto-exposure/focus)
        await new Promise(r => setTimeout(r, 500));

        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);

        // 4. Stop the camera immediately
        stream.getTracks().forEach(t => t.stop());

        // 5. Convert to base64 JPEG
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        const base64 = dataUrl.split(',')[1];

        // 6. Deliver to backend with nonce
        const result = await fetchWithTimeout('/api/plugin/webcam/capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nonce: pending.nonce,
                data: base64,
                media_type: 'image/jpeg'
            })
        });

        if (result?.status === 'ok') {
            console.log('[Webcam] Capture delivered to backend');
        } else {
            console.warn('[Webcam] Backend rejected capture:', result?.error);
        }

    } catch (err) {
        console.error('[Webcam] Capture failed:', err);
    } finally {
        capturing = false;
    }
}

export default {
    init() {
        document.addEventListener('sapphire:tool_start', onToolStart);
        console.log('[Webcam] Plugin script loaded');
    }
};
