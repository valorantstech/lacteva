/**
 * What a role is called to the people who hold it (WO-104 §3, WO-108 §1).
 *
 * The registry's keys — `tenant-admin`, `DRIVER`, `CENTRE_MANAGER` — are the
 * platform's. Under a shopkeeper's name the header says "Owner"; the invite
 * form offers "Delivery boy", because that is what the owner is hiring. Every
 * other key reads as words. One function, used by the shell, the Staff page
 * and anything else that names a role.
 */
const LABELS: Record<string, string> = {
  "tenant-admin": "Owner",
  ORGANIZATION_ADMIN: "Owner",
  DRIVER: "Delivery boy",
  CUSTOMER_PORTAL: "Customer",
  "tenant-viewer": "Viewer",
};

export const OWNER_ROLES = new Set(["tenant-admin", "ORGANIZATION_ADMIN"]);

export function roleLabel(name: string): string {
  if (LABELS[name]) return LABELS[name];
  return name
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
