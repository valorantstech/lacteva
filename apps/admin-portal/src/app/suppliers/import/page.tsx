"use client";

import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { CsvImport } from "@/components/csv-import";

/** The farmer list, loaded from the dairy's own spreadsheet (P0-PILOT-003). */
export default function SupplierImportPage() {
  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[
          { label: "Suppliers", href: "/suppliers" },
          { label: "Import" },
        ]}
        title="Import suppliers"
        description="Load the dairy's farmer list from CSV. Each row is validated by the platform individually — one bad row fails alone, with its reason."
      />
      <CsvImport kind="suppliers" />
    </PageContainer>
  );
}
