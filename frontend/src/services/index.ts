// Backend integration modules.
// Each domain gets its own service here (auth.ts, campaigns.ts, prospects.ts),
// calling src/lib/api-client.ts. Keep pages/components free of raw fetch calls.

// Example module shape:
// export async function getCampaigns(): Promise<Campaign[]> {
//   return apiFetch<Campaign[]>("/campaigns");
// }
export {};
