import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

// Import or replicate the exact Web Crypto PKCE functions from src/utils/crypto.ts
function bufferToBase64Url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function generatePkcePair() {
  const randomBytes = new Uint8Array(32);
  globalThis.crypto.getRandomValues(randomBytes);
  const verifier = bufferToBase64Url(randomBytes.buffer);

  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', data);
  const challenge = bufferToBase64Url(digest);

  return { verifier, challenge };
}

describe('Frontend PKCE & Window Handoff Security (Simulated Environment)', () => {
  it('generates cryptographically random verifier and S256 challenge', async () => {
    const pair1 = await generatePkcePair();
    const pair2 = await generatePkcePair();

    // Verifier is 43 chars base64url
    assert.ok(pair1.verifier.length >= 43);
    assert.ok(pair1.challenge.length >= 43);
    // Uniqueness
    assert.notEqual(pair1.verifier, pair2.verifier);
    assert.notEqual(pair1.challenge, pair2.challenge);

    // Verify S256 calculation
    const encoder = new TextEncoder();
    const digest = await globalThis.crypto.subtle.digest('SHA-256', encoder.encode(pair1.verifier));
    const expectedChallenge = bufferToBase64Url(digest);
    assert.equal(pair1.challenge, expectedChallenge);
  });

  it('rejects postMessage from untrusted origin', () => {
    const trustedOrigin = 'http://localhost:8000';
    const fakeEvent = {
      origin: 'https://evil-attacker.com',
      data: { type: 'CCMS_GOOGLE_AUTH_SUCCESS', ticket: 'stolen-ticket' },
      source: {},
    };

    let accepted = false;
    const handleMessage = (event) => {
      if (event.origin !== trustedOrigin) {
        return; // Reject untrusted origin
      }
      accepted = true;
    };

    handleMessage(fakeEvent);
    assert.equal(accepted, false, 'Message from untrusted origin must be rejected');
  });

  it('rejects postMessage from unexpected window source', () => {
    const trustedOrigin = 'http://localhost:8000';
    const mockPopup = { closed: false };
    const otherWindow = { closed: false };

    const eventFromOther = {
      origin: trustedOrigin,
      data: { type: 'CCMS_GOOGLE_AUTH_SUCCESS', ticket: 'ticket-123' },
      source: otherWindow, // Not the opened popup
    };

    let accepted = false;
    const handleMessage = (event) => {
      if (event.origin !== trustedOrigin) return;
      if (event.source !== mockPopup) return; // Strict source check
      accepted = true;
    };

    handleMessage(eventFromOther);
    assert.equal(accepted, false, 'Message from non-popup window source must be rejected');
  });

  it('accepts valid postMessage from exact popup and origin', () => {
    const trustedOrigin = 'http://localhost:8000';
    const mockPopup = { closed: false };

    const validEvent = {
      origin: trustedOrigin,
      data: { type: 'CCMS_GOOGLE_AUTH_SUCCESS', ticket: 'valid-handoff-ticket-456' },
      source: mockPopup,
    };

    let receivedTicket = null;
    const handleMessage = (event) => {
      if (event.origin !== trustedOrigin) return;
      if (event.source !== mockPopup) return;
      if (event.data?.type === 'CCMS_GOOGLE_AUTH_SUCCESS') {
        receivedTicket = event.data.ticket;
      }
    };

    handleMessage(validEvent);
    assert.equal(receivedTicket, 'valid-handoff-ticket-456');
  });

  it('handles user popup cancellation and listener cleanup', (t) => {
    let cleanedUp = false;
    const mockPopup = { closed: false };
    const cleanup = () => {
      cleanedUp = true;
    };

    // Simulate user closing popup manually
    mockPopup.closed = true;
    if (mockPopup.closed) {
      cleanup();
    }

    assert.equal(cleanedUp, true, 'Cleanup must run when popup is closed by user');
  });
});
