"use client";

import { PageHeader } from "@/components/page-header";
import { CsvImport } from "@/components/csv-import";

/** The outlet list with standing orders, from CSV (P0-PILOT-003). */
export default function CustomerImportPage() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[{ label: "Customers", href: "/customers" }, { label: "Import" }]}
        title="Import customers"
        description="Load the outlet list from CSV — each row may carry its standing order. Re-importing the same file names the duplicates instead of creating them twice."
      />
      <CsvImport kind="customers" />
    </div>
  );
}
