import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Chip, Stack, Typography, useTheme } from "@mui/material";
import ForceGraph2D from "react-force-graph-2d";

import { NODE_COLORS } from "@/theme";
import type { GraphView } from "@/types";

interface ForceNode {
  id: string;
  name: string;
  label: string;
  val: number;
  color: string;
  x?: number;
  y?: number;
}

interface ForceLink {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export default function GraphCanvas({
  view,
  height = 560,
  onNodeClick,
}: {
  view: GraphView;
  height?: number;
  onNodeClick?: (node: { id: string; label: string; name: string }) => void;
}) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(900);
  const [hovered, setHovered] = useState<ForceNode | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const data = useMemo(() => {
    const degree = new Map<string, number>();
    view.edges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    });
    const nodes: ForceNode[] = view.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      label: node.label,
      val: 2 + Math.min(10, (degree.get(node.id) ?? 0) / 2),
      color: NODE_COLORS[node.label] ?? "#94a3b8",
    }));
    const ids = new Set(nodes.map((node) => node.id));
    const links: ForceLink[] = view.edges
      .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
      .map((edge) => ({
        source: edge.source,
        target: edge.target,
        relation: edge.relation,
        weight: edge.weight,
      }));
    return { nodes, links };
  }, [view]);

  const legend = useMemo(() => {
    const counts = new Map<string, number>();
    view.nodes.forEach((node) => counts.set(node.label, (counts.get(node.label) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [view.nodes]);

  return (
    <Box>
      <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
        {legend.map(([label, count]) => (
          <Chip
            key={label}
            size="small"
            label={`${label} · ${count}`}
            sx={{
              bgcolor: `${NODE_COLORS[label] ?? "#94a3b8"}22`,
              color: NODE_COLORS[label] ?? "text.primary",
              fontWeight: 600,
            }}
          />
        ))}
      </Stack>

      <Box
        ref={containerRef}
        sx={{
          position: "relative",
          height,
          borderRadius: 3,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
          bgcolor: theme.palette.mode === "light" ? "#fbfcfe" : "#0d1426",
        }}
      >
        <ForceGraph2D
          width={width}
          height={height}
          graphData={data}
          cooldownTicks={90}
          backgroundColor="rgba(0,0,0,0)"
          nodeRelSize={4}
          nodeLabel={(node: ForceNode) => `${node.label}: ${node.name}`}
          linkColor={() => (theme.palette.mode === "light" ? "rgba(100,116,139,0.28)" : "rgba(148,163,184,0.25)")}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          linkWidth={(link: ForceLink) => 0.4 + link.weight}
          onNodeHover={(node: ForceNode | null) => setHovered(node)}
          onNodeClick={(node: ForceNode) =>
            onNodeClick?.({ id: node.id, label: node.label, name: node.name })
          }
          nodeCanvasObject={(node: ForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const radius = Math.max(3, node.val * 0.7);
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
            ctx.fillStyle = node.color;
            ctx.fill();

            if (globalScale > 1.1 || node.val > 7) {
              const fontSize = Math.max(9, 11 / globalScale);
              ctx.font = `${fontSize}px Inter, sans-serif`;
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.fillStyle = theme.palette.text.primary;
              const label = node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name;
              ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + radius + 2);
            }
          }}
        />

        {hovered ? (
          <Box
            sx={{
              position: "absolute",
              left: 12,
              bottom: 12,
              px: 1.5,
              py: 1,
              borderRadius: 2,
              bgcolor: "background.paper",
              border: "1px solid",
              borderColor: "divider",
              maxWidth: 320,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              {hovered.label}
            </Typography>
            <Typography variant="subtitle2">{hovered.name}</Typography>
          </Box>
        ) : null}
      </Box>

      {view.truncated ? (
        <Typography variant="caption" color="text.secondary">
          View truncated for readability — narrow the focus or lower the depth to see everything.
        </Typography>
      ) : null}
    </Box>
  );
}
