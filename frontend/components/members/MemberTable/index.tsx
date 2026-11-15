import type { Member } from "@/lib/api";
import Pagination from "@/components/ui/Pagination";
import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";

export default function MemberTable({
  members,
  loading,
  listError,
  skip,
  total,
  limit,
  onPageChange,
  onOpenDetails,
}: {
  members: Member[];
  loading: boolean;
  listError: string | null;
  skip: number;
  total: number;
  limit: number;
  onPageChange: (newSkip: number) => void;
  onOpenDetails: (member: Member) => void;
}) {
  return (
    <section>
      {loading ? (
        <p>Loading...</p>
      ) : listError ? (
        <p>Unable to load members.</p>
      ) : members.length === 0 ? (
        <p>No matching records found.</p>
      ) : (
        <>
          <Table>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>PSN</th>
                <th>Name</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{m.psn?.replace("MCT-", "") ?? ""}</td>
                  <td>
                    {m.name}
                    {/* A conflicted member's record stays in the list --
                        this officer just isn't the one who may change it. */}
                    {m.conflicted && (
                      <div style={{ fontSize: 12 }}>
                        <ConflictMarker />
                      </div>
                    )}
                  </td>
                  {/* The rest of the record, and every action on it, lives in
                      the details modal behind this link. */}
                  <td>
                    <button type="button" className="link-button" onClick={() => onOpenDetails(m)}>
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination skip={skip} limit={limit} total={total} onChange={onPageChange} />
        </>
      )}
    </section>
  );
}
