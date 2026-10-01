import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
import sharp from "sharp";
import { fitTitleFontSize, formatMonthYear } from "./title.mjs";

export const CANVAS_WIDTH = 1200;
export const CANVAS_HEIGHT = 630;
const PADDING_Y = 72;
const PADDING_X = 88;
export const IMAGE_SIZE = 360;
const RENDER_SCALE = 2;

export function buildCardTree({ title, categoryName, monthYear, illustrationDataUri, brand, fonts }) {
  const contentHeight = CANVAS_HEIGHT - PADDING_Y * 2;
  const leftWidth = CANVAS_WIDTH - PADDING_X * 2 - IMAGE_SIZE - 40;
  const titleFontSize = fitTitleFontSize(title, leftWidth, 3);
  const meta = [categoryName, monthYear].filter(Boolean).join(" · ");

  return {
    type: "div",
    props: {
      style: {
        display: "flex",
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        background: brand.background,
        padding: `${PADDING_Y}px ${PADDING_X}px`,
        fontFamily: fonts.title.family,
      },
      children: [
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              flexDirection: "column",
              justifyContent: "flex-start",
              width: leftWidth,
              height: contentHeight,
            },
            children: [
              {
                type: "div",
                props: {
                  style: { display: "flex" },
                  children: meta
                    ? [
                        {
                          type: "span",
                          props: {
                            style: {
                              fontFamily: fonts.meta.family,
                              fontWeight: fonts.meta.weight,
                              fontSize: 22,
                              color: brand.muted,
                              letterSpacing: -0.2,
                            },
                            children: meta,
                          },
                        },
                      ]
                    : [],
                },
              },
              {
                type: "div",
                props: {
                  style: {
                    display: "flex",
                    marginTop: 20,
                    fontFamily: fonts.title.family,
                    fontWeight: fonts.title.weight,
                    fontSize: titleFontSize,
                    lineHeight: 1.15,
                    letterSpacing: -1,
                    color: brand.text,
                  },
                  children: title,
                },
              },
              { type: "div", props: { style: { display: "flex", flexGrow: 1 }, children: [] } },
              {
                type: "div",
                props: {
                  style: { display: "flex", flexDirection: "column" },
                  children: [
                    {
                      type: "div",
                      props: {
                        style: { display: "flex", alignItems: "center" },
                        children: [
                          {
                            type: "span",
                            props: {
                              style: {
                                fontFamily: fonts.byline.family,
                                fontWeight: fonts.byline.weight,
                                fontSize: 30,
                                color: brand.text,
                              },
                              children: brand.byline,
                            },
                          },
                          {
                            type: "div",
                            props: {
                              style: {
                                display: "flex",
                                width: 10,
                                height: 30,
                                marginLeft: 6,
                                background: brand.accent,
                              },
                              children: [],
                            },
                          },
                        ],
                      },
                    },
                    {
                      type: "span",
                      props: {
                        style: {
                          display: "flex",
                          marginTop: 6,
                          fontFamily: fonts.meta.family,
                          fontWeight: fonts.meta.weight,
                          fontSize: 22,
                          color: brand.accent,
                        },
                        children: brand.url,
                      },
                    },
                  ],
                },
              },
            ],
          },
        },
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              width: IMAGE_SIZE,
              height: IMAGE_SIZE,
              marginLeft: 40,
              alignSelf: "center",
              borderRadius: 28,
              overflow: "hidden",
              background: "#f5f5f5",
            },
            children: [
              {
                type: "img",
                props: {
                  src: illustrationDataUri,
                  width: IMAGE_SIZE,
                  height: IMAGE_SIZE,
                  style: { objectFit: "cover" },
                },
              },
            ],
          },
        },
      ],
    },
  };
}

export async function renderCard({ post, categoryName, illustrationPngBuffer, fontData, brand, fonts }) {
  const squareBuffer = await sharp(illustrationPngBuffer)
    .resize(IMAGE_SIZE * RENDER_SCALE, IMAGE_SIZE * RENDER_SCALE, { fit: "cover" })
    .png()
    .toBuffer();
  const illustrationDataUri = `data:image/png;base64,${squareBuffer.toString("base64")}`;

  const tree = buildCardTree({
    title: post.title,
    categoryName,
    monthYear: formatMonthYear(post.date),
    illustrationDataUri,
    brand,
    fonts,
  });

  const svg = await satori(tree, { width: CANVAS_WIDTH, height: CANVAS_HEIGHT, fonts: fontData });
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: CANVAS_WIDTH * RENDER_SCALE } });
  const rendered = resvg.render().asPng();
  return sharp(rendered).resize(CANVAS_WIDTH, CANVAS_HEIGHT).png().toBuffer();
}
