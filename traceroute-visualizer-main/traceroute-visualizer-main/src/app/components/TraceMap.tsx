"use client";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { classifyHop, Hop } from "../utils/tracerouteClassification";
import { MergedHopView } from "../utils/multiProbe";

// Optional: fix missing marker icons in Leaflet
const iconUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png';
const iconShadowUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl,
  shadowUrl: iconShadowUrl,
});
L.Marker.prototype.options.icon = DefaultIcon;

type TraceMapProps = {
  hops: Hop[];
  target: string;
  hopViews?: MergedHopView[];
};

const stateLabels: Record<MergedHopView["state"], string> = {
  responsive: "🟢 Responsive",
  filtered: "🟡 Filtered",
  unreachable: "🔴 Unreachable",
};

export default function TraceMap({ hops, target, hopViews }: TraceMapProps) {
  const resolvedHops = hopViews?.length
    ? hopViews
        .map(view => {
          const bestHop = view.bestHop?.hop;
          if (!bestHop) return null;
          return { hop: bestHop, view };
        })
        .filter((entry): entry is { hop: Hop; view: MergedHopView } => entry !== null)
    : hops.map(hop => ({ hop, view: undefined }));
  const validHops = resolvedHops.filter(
    entry => entry.hop.geo && entry.hop.geo.lat != null && entry.hop.geo.lon != null,
  );
  const positions = validHops.map(
    entry => [entry.hop.geo.lat!, entry.hop.geo.lon!] as [number, number],
  );

  if (positions.length === 0) return null;

  const center = positions[0];

  return (
    <MapContainer
      center={center}
      zoom={2}
      scrollWheelZoom={true}
      style={{ height: "500px", width: "100%", marginTop: "2rem" }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />

      {validHops.map((entry, idx) => {
        const hop = entry.hop;
        const lat = hop.geo?.lat;
        const lon = hop.geo?.lon;
        if (lat == null || lon == null) return null;
        const classification = classifyHop(hop, target);
        const popupStatus = entry.view ? stateLabels[entry.view.state] : null;
        const popupReason = entry.view?.reasonParts.slice(0, 3).join(" ");
        return (
          <Marker key={idx} position={[lat, lon]} icon={DefaultIcon}>
            <Popup>
              <strong>Hop {hop.hop}</strong><br />
              {popupStatus && (
                <>
                  {popupStatus}
                  <br />
                </>
              )}
              {hop.hostname} ({hop.ip})<br />
             {classification.ownership && (
                  <>
                    📍 {classification.ownership.label}
                    {classification.ownership.city ? ` (${classification.ownership.city})` : ""}
                    <br />
                 </>
              )}     
         
              {hop.latency}<br />
              {popupReason || classification.explanation || "Hop details available."}
            </Popup>
          </Marker>
        );
      })}

      <Polyline positions={positions} color="blue" />
    </MapContainer>
  );
}
