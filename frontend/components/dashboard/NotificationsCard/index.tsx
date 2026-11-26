import type { Notification, NotificationPage } from "@/lib/api";

import styles from "../dashboard.module.css";

function when(value: string) {
  // Timestamps are naive UTC; without the suffix the browser reads them as
  // local time and prints the wrong hour.
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

function Note({ note }: { note: Notification }) {
  const content = (
    <>
      <p className={styles.notificationTitle}>
        {!note.is_read && <span className={styles.unreadDot} aria-hidden="true" />}
        {note.title}
      </p>
      {note.body && <p className={styles.notificationBody}>{note.body}</p>}
      <p className={styles.notificationTime}>{when(note.created_at)}</p>
    </>
  );

  return (
    <li className={styles.notificationItem}>
      {note.link_path ? (
        <a className={styles.notificationLink} href={note.link_path}>
          {content}
        </a>
      ) : (
        content
      )}
    </li>
  );
}

export default function NotificationsCard({ page }: { page: NotificationPage | null }) {
  return (
    <section id="notifications" className={`${styles.panel} ${styles.anchor}`}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>Notifications</h2>
        {page && page.unread_count > 0 && (
          <span className={`${styles.chip} ${styles.chipPending}`}>
            {page.unread_count} unread
          </span>
        )}
      </div>

      {!page || page.items.length === 0 ? (
        <p className={styles.empty}>
          {page ? "No notifications yet." : "Notifications could not be loaded just now."}
        </p>
      ) : (
        <ul className={styles.notificationList}>
          {page.items.slice(0, 3).map((note) => (
            <Note key={note.id} note={note} />
          ))}
        </ul>
      )}
    </section>
  );
}
