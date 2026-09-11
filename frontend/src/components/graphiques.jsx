/**
 * Graphiques de l'application.
 *
 * DEUX ROLES DE COULEUR, DEUX TRAITEMENTS - et un seul de chaque :
 *
 *  1. MAGNITUDE (repartition par categorie) : une seule teinte.
 *     Ces barres comparent des quantites, pas des identites ; leur donner une
 *     couleur par barre ferait croire a une signification qui n'existe pas.
 *
 *  2. STATUT (paliers de criticite) : la palette de severite du theme,
 *     rouge -> orange -> ambre -> gris. Elle est reservee a cet usage et
 *     n'est jamais reemployee comme "serie 3".
 *
 * Note sur la severite : quatre paliers dans une gamme chaude ne peuvent pas
 * etre tous separes de maniere maximale - rouge et orange restent proches
 * (ΔE 10,4 en vision normale). C'est acceptable ICI, et seulement ici, parce
 * que la couleur n'est jamais le seul porteur d'information : chaque barre
 * porte son libelle en axe, chaque pastille porte son texte. Le contraste de
 * chacune des quatre teintes sur le fond sombre a ete verifie (>= 3:1).
 * C'est aussi la palette deja etablie dans le theme : la changer
 * desynchroniserait les listes, les alertes et les rapports.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const COULEUR_NIVEAU = {
  critique: "#EF4444",
  elevee: "#F97316",
  moyenne: "#F59E0B",
  faible: "#94A3B8",
};

const ACCENT = "#00E5C0";
const GRILLE = "#1E2D4A";
const TEXTE_AXE = "#64748B";

/** Infobulle sobre, aux couleurs des surfaces de l'application. */
function Infobulle({ active, payload, label, suffixe = "" }) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--r-sm)",
        padding: "7px 11px",
        boxShadow: "var(--shadow-md)",
        fontSize: 12,
      }}
    >
      <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ color: "var(--text-primary)", fontWeight: 600 }}>
        {payload[0].value} {suffixe}
      </div>
    </div>
  );
}

/**
 * Barres horizontales. L'horizontale est choisie parce que les libelles
 * ("Administration publique", "Données personnelles") sont longs : en
 * vertical ils seraient tronques ou inclines.
 */
export function BarresHorizontales({
  donnees,
  couleurParCle = null,
  hauteurParBarre = 30,
  suffixe = "élément(s)",
}) {
  if (!donnees || donnees.length === 0) {
    return (
      <div className="cell-muted" style={{ padding: "24px 0", fontSize: 12.5 }}>
        Aucune donnée sur cette période.
      </div>
    );
  }

  const hauteur = Math.max(140, donnees.length * hauteurParBarre + 24);

  return (
    <ResponsiveContainer width="100%" height={hauteur}>
      <BarChart
        data={donnees}
        layout="vertical"
        margin={{ top: 4, right: 30, bottom: 4, left: 4 }}
        barCategoryGap="22%"
      >
        {/* Grille discrete : elle sert a lire les valeurs, pas a se faire
            remarquer. Uniquement verticale, l'axe des quantites. */}
        <CartesianGrid
          horizontal={false}
          stroke={GRILLE}
          strokeDasharray="2 4"
        />
        <XAxis
          type="number"
          allowDecimals={false}
          tick={{ fill: TEXTE_AXE, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="libelle"
          width={168}
          tick={{ fill: "#A0AEC0", fontSize: 11.5 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          content={<Infobulle suffixe={suffixe} />}
          cursor={{ fill: "rgba(28, 43, 73, 0.45)" }}
        />
        <Bar dataKey="valeur" radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {donnees.map((ligne) => (
            <Cell
              key={ligne.libelle}
              fill={couleurParCle ? couleurParCle(ligne) : ACCENT}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
