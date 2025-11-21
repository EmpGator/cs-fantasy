// ==UserScript==
// @name         HLTV Cookie Sync
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Automatically sync Cloudflare cookies from HLTV to your FantasyGator server
// @author       FantasyGator
// @match        https://www.hltv.org/*
// @match        https://hltv.org/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @grant        GM_cookie
// @connect      localhost
// @connect      127.0.0.1
// ==/UserScript==

(function() {
    'use strict';

    // ============================================
    // CONFIGURATION - Update these values!
    // ============================================

    // Your FantasyGator server URL
    const SERVER_URL = 'http://localhost:7000';

    // API endpoint for cookie submission
    const COOKIE_ENDPOINT = '/api/cookies/cloudflare/';

    // How often to sync cookies (in milliseconds)
    // Default: 10 minutes (cookies typically last 15-30 minutes)
    const SYNC_INTERVAL = 10 * 60 * 1000;

    // Show notifications on sync
    const SHOW_NOTIFICATIONS = true;

    // ============================================
    // Cookie extraction (using GM_cookie for HttpOnly cookies)
    // ============================================

    function extractAndSubmitCookies() {
        // GM_cookie.list gets all cookies including HttpOnly
        // partitionKey needed for CHIPS (partitioned cookies like cf_clearance)
        GM_cookie.list({
            domain: '.hltv.org',
            partitionKey: { topLevelSite: 'https://hltv.org' }
        }, function(cookies) {
            if (!cookies || cookies.length === 0) {
                console.log('[HLTV Cookie Sync] No cookies found for .hltv.org');
                return;
            }

            const cookieData = {
                cf_clearance: null,
                cf_bm: null,
                user_agent: navigator.userAgent,
                domain: 'www.hltv.org'
            };

            for (const cookie of cookies) {
                if (cookie.name === 'cf_clearance') {
                    cookieData.cf_clearance = cookie.value;
                } else if (cookie.name === '__cf_bm') {
                    cookieData.cf_bm = cookie.value;
                }
            }

            if (!cookieData.cf_clearance) {
                console.log('[HLTV Cookie Sync] No cf_clearance cookie found');
                return;
            }

            submitCookies(cookieData);
        });
    }

    // ============================================
    // Cookie submission
    // ============================================

    function submitCookies(cookies) {
        console.log('[HLTV Cookie Sync] Submitting cookies to server...');

        GM_xmlhttpRequest({
            method: 'POST',
            url: SERVER_URL + COOKIE_ENDPOINT,
            headers: {
                'Content-Type': 'application/json'
            },
            data: JSON.stringify(cookies),
            onload: function(response) {
                if (response.status === 200) {
                    try {
                        const data = JSON.parse(response.responseText);
                        console.log('[HLTV Cookie Sync] Success:', data.message);

                        if (SHOW_NOTIFICATIONS) {
                            GM_notification({
                                title: 'HLTV Cookie Sync',
                                text: data.message,
                                timeout: 3000
                            });
                        }
                    } catch (e) {
                        console.error('[HLTV Cookie Sync] Invalid JSON response:', response.responseText.substring(0, 200));
                    }
                } else if (response.status === 403) {
                    console.error('[HLTV Cookie Sync] Authentication required. Make sure you are logged in as staff on', SERVER_URL);
                } else if (response.status === 302 || response.status === 0) {
                    console.error('[HLTV Cookie Sync] Redirect to login. Make sure you are logged in as staff on', SERVER_URL);
                } else {
                    console.error('[HLTV Cookie Sync] Failed:', response.status, response.responseText.substring(0, 200));
                }
            },
            onerror: function(error) {
                console.error('[HLTV Cookie Sync] Network error:', error);
            }
        });
    }

    // ============================================
    // Main
    // ============================================

    // Initial sync on page load
    setTimeout(extractAndSubmitCookies, 2000);

    // Periodic sync
    setInterval(extractAndSubmitCookies, SYNC_INTERVAL);

    // Also sync when tab becomes visible (in case user returns after a while)
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            extractAndSubmitCookies();
        }
    });

    console.log('[HLTV Cookie Sync] Userscript loaded. Will sync cookies every', SYNC_INTERVAL / 1000 / 60, 'minutes');
})();
