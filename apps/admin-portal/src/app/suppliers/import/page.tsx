"use client";

import { PageHeader } from "@/components/page-header";
import { CsvImport } from "@/components/csv-import";

/** The farmer list, loaded from the dairy's own spreadsheet (P0-PILOT-003). */
export default function SupplierImportPage() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[{ label: "Suppliers", href: "/suppliers" }, { label: "Import" }]}
        title="Import suppliers"
        description="Load the dairy's farmer list from CSV. Each row is validated by the platform individually — one bad row fails alone, with its reason."
      />
      <CsvImport kind="suppliers" />
    </div>
  );
}
