import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function options(argv) {
  const result = { source: "", output: "", documents: 0 };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--source") result.source = argv[++index];
    else if (value === "--output") result.output = argv[++index];
    else if (value === "--documents") result.documents = Number(argv[++index]);
    else throw new Error(`未知參數：${value}`);
  }
  if (!result.source || !result.output || !Number.isInteger(result.documents)) {
    throw new Error("需要 --source、--output 與整數 --documents");
  }
  if (result.documents < 1 || result.documents > 5000) {
    throw new Error("容量測試文件數必須是 1 到 5000");
  }
  return result;
}

async function main({ source, output, documents }) {
  const payload = JSON.parse(await readFile(path.resolve(source), "utf8"));
  const template = payload.documents?.[0];
  if (payload.schema_version !== 1 || !template?.sections?.length) {
    throw new Error("容量來源必須含有至少一份結構化仿單");
  }
  const clones = [];
  for (let index = 1; index <= documents; index += 1) {
    const suffix = String(index).padStart(6, "0");
    clones.push({
      ...structuredClone(template),
      id: `CAPACITY-${suffix}:1`,
      license_no: `容量測試字第${suffix}號`,
      drug_name_zh: `容量測試藥品 ${suffix}`,
      drug_name_en: `CAPACITY TEST DRUG ${suffix}`,
      version: "1",
      source_kind: "synthetic_capacity_fixture",
    });
  }
  const result = {
    schema_version: 1,
    retrieved_at: new Date().toISOString(),
    source: {
      provider: "Synthetic capacity fixture cloned from one real TFDA structure sample",
      source_file: path.basename(source),
      warning: "Not representative coverage or clinical data",
    },
    document_count: clones.length,
    documents: clones,
  };
  const outputPath = path.resolve(output);
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(result)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify({ output: outputPath, documents: clones.length, sections: clones.reduce((sum, item) => sum + item.sections.length, 0) })}\n`);
}

try {
  await main(options(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
