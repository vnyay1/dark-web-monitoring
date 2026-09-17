/**
 * Tri de tableau cote client, accessible.
 *
 * L'en-tete triable porte aria-sort sur le <th> et un vrai <button> : le tri
 * se fait au clavier et son sens est annonce ("trie par ordre croissant").
 */

import { useMemo, useState } from "react";

import { IconeBas, IconeHaut, IconeTri } from "./icones";

/**
 * lignes      : tableau a trier
 * accesseurs  : { cle: (ligne) => valeur comparable }
 * initial     : { cle, sens: "asc" | "desc" }
 */
export function useTri(lignes, accesseurs, initial = null) {
  const [tri, setTri] = useState(initial);

  const triees = useMemo(() => {
    if (!tri || !lignes) return lignes || [];
    const acceder = accesseurs[tri.cle];
    const facteur = tri.sens === "asc" ? 1 : -1;
    return [...lignes].sort((a, b) => {
      const va = acceder(a);
      const vb = acceder(b);
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      return (va < vb ? -1 : 1) * facteur;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lignes, tri]);

  function trierPar(cle) {
    setTri((actuel) =>
      actuel?.cle === cle
        ? { cle, sens: actuel.sens === "asc" ? "desc" : "asc" }
        : { cle, sens: "desc" },
    );
  }

  return { triees, tri, trierPar };
}

export function EnTeteTri({ cle, tri, trierPar, children, className }) {
  const actif = tri?.cle === cle;
  const sens = actif ? (tri.sens === "asc" ? "ascending" : "descending") : "none";
  const Icone = !actif ? IconeTri : tri.sens === "asc" ? IconeHaut : IconeBas;

  return (
    <th scope="col" aria-sort={sens} className={className}>
      <button type="button" className="tri" onClick={() => trierPar(cle)}>
        {children}
        <Icone taille={14} />
      </button>
    </th>
  );
}
