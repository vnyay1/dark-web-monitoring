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
 *     reservee a cet usage et jamais reemployee comme "serie 3".
 *
 * La couleur n'est jamais le seul porteur d'information : chaque barre porte
 * son libelle en axe. Les couleurs sont LUES dans les variables du theme
 * actif (tokens.css), ou leur contraste sur la surface est verifie (>= 3:1)
 * dans les deux themes ; elles changent donc avec l'interrupteur.
 *
 * Alternative textuelle : chaque graphique est double d'un tableau reserve
 * aux lecteurs d'ecran, et le SVG est masque pour eux.
 */

import { useEffect, useState } from "react";
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

import { useTheme } from "../theme/theme";

const VARIABLES = {
  critique: "--niveau-critique",
  elevee: "--niveau-elevee",
  moyenne: "--niveau-moyenne",
  faible: "--graphique-faible",
  barre: "--graphique-barre",
  grille: "--graphique-grille",
  axe: "--graphique-axe",
  libelle: "--graphique-libelle",
  survol: "--bg-hover",
};

function lireCouleurs() {
  const styles = getComputedStyle(document.documentElement);
  return Object.fromEntries(
    Object.entries(VARIABLES).map(([nom, variable]) => [nom, styles.getPropertyValue(variable).trim()]),
  );
}

/** Couleurs du theme actif, relues a chaque bascule de theme. */
export function useCouleursGraphique() {
  const { theme } = useTheme();
  const [couleurs, setCouleurs] = useState(lireCouleurs);
  useEffect(() => {
    setCouleurs(lireCouleurs());
  }, [theme]);
  return couleurs;
}

/** Infobulle aux couleurs des surfaces de l'application. */
function Infobulle({ active, payload, label, suffixe = "" }) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="infobulle-graphique">
      <div className="infobulle-graphique-libelle">{label}</div>
      <div className="infobulle-graphique-valeur">
        {payload[0].value} {suffixe}
      </div>
    </div>
  );
}

/**
 * Barres horizontales. L'horizontale est choisie parce que les libelles
 * ("Agence gouvernementale", "Télécommunications") sont longs : en vertical
 * ils seraient tronques ou inclines.
 *
 * cleCouleur(ligne) : nom de couleur du theme (ex. "critique") ; par defaut
 * la teinte unique de magnitude.
 */
export function BarresHorizontales({
  donnees,
  cleCouleur = null,
  hauteurParBarre = 32,
  suffixe = "élément(s)",
  titre,
}) {
  const couleurs = useCouleursGraphique();

  if (!donnees || donnees.length === 0) {
    return <p className="texte-aide graphique-vide">Aucune donnée sur cette période.</p>;
  }

  const hauteur = Math.max(140, donnees.length * hauteurParBarre + 24);

  return (
    <>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={hauteur}>
          <BarChart
            data={donnees}
            layout="vertical"
            margin={{ top: 4, right: 30, bottom: 4, left: 4 }}
            barCategoryGap="24%"
          >
            <CartesianGrid horizontal={false} stroke={couleurs.grille} strokeDasharray="2 4" />
            <XAxis
              type="number"
              allowDecimals={false}
              tick={{ fill: couleurs.axe, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="libelle"
              width={172}
              tick={{ fill: couleurs.libelle, fontSize: 13 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<Infobulle suffixe={suffixe} />} cursor={{ fill: couleurs.survol }} />
            <Bar dataKey="valeur" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {donnees.map((ligne) => (
                <Cell
                  key={ligne.libelle}
                  fill={cleCouleur ? couleurs[cleCouleur(ligne)] : couleurs.barre}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="sr-only">
        {titre && <caption>{titre}</caption>}
        <thead>
          <tr>
            <th scope="col">Libellé</th>
            <th scope="col">Nombre</th>
          </tr>
        </thead>
        <tbody>
          {donnees.map((ligne) => (
            <tr key={ligne.libelle}>
              <th scope="row">{ligne.libelle}</th>
              <td>{ligne.valeur}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
