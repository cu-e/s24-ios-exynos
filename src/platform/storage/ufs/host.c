#include "host.h"
static uint32_t le16(const uint8_t *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8); }
static uint32_t le32(const uint8_t *p) { return le16(p)|(le16(p+2)<<16); }
static uint64_t le64(const uint8_t *p) { return le32(p)|((uint64_t)le32(p+4)<<32); }
static uint32_t be32(const uint8_t *p) { return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
static void put16(uint8_t *p, uint32_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p, uint32_t v) { put16(p,v); put16(p+2,v>>16); }
static void put64(uint8_t *p, uint64_t v) { put32(p,(uint32_t)v); put32(p+4,(uint32_t)(v>>32)); }
static void putbe32(uint8_t *p, uint32_t v) { p[0]=(uint8_t)(v>>24); p[1]=(uint8_t)(v>>16); p[2]=(uint8_t)(v>>8); p[3]=(uint8_t)v; }
static uint32_t policy_valid(const struct ufs_policy *p)
{
    if (!p || !p->epoch || p->lun>127 || p->sqid>31 ||
        (p->block_bytes!=512 && p->block_bytes!=4096) || !p->lun_blocks ||
        !p->extent_blocks || p->first_block>=p->lun_blocks ||
        p->extent_blocks>p->lun_blocks-p->first_block) return UFS_ARGUMENT;
    if (!p->ucd_dma || !p->data_dma || (p->ucd_dma&127) || (p->data_dma&3) ||
        p->ucd_bytes<UFS_UCD_BYTES || p->data_bytes<UFS_MAX_TRANSFER ||
        p->ucd_bytes>UINT64_MAX-p->ucd_dma || p->data_bytes>UINT64_MAX-p->data_dma)
        return UFS_DMA_RANGE;
    /* All caller-qualified DMA regions must be disjoint, not merely the
       bytes occupied by this request. No address is mapped or probed. */
    if (p->ucd_dma<p->data_dma+p->data_bytes && p->data_dma<p->ucd_dma+p->ucd_bytes)
        return UFS_DMA_RANGE;
    return UFS_OK;
}
static uint32_t token_valid(const struct ufs_host *h, const struct ufs_token *t)
{
    return t && t->epoch==h->token.epoch && t->generation==h->token.generation &&
        t->tag==h->token.tag && t->generation;
}
uint32_t ufs_host_init(struct ufs_host *h, const struct ufs_policy *p)
{
    struct ufs_host value={0};
    uint32_t r;
    if (!h) return UFS_ARGUMENT;
    r=policy_valid(p);
    if (r) { *h=value; return r; }
    value.policy=*p; value.token.epoch=p->epoch; *h=value;
    return UFS_OK;
}
uint32_t ufs_host_prepare(struct ufs_host *h, const uint8_t *cdb, size_t length,
    uint32_t direction, uint64_t expected_bytes)
{
    struct ufs_packet packet={0};
    uint64_t lba, count, bytes;
    uint32_t i,done=0,entries,tag,r;
    if (!h || !cdb) return UFS_ARGUMENT;
    r=policy_valid(&h->policy); if (r) return r;
    if (h->phase!=UFS_IDLE) return UFS_BUSY;
    if (direction!=UFS_FROM_DEVICE) return UFS_WRITE_REJECTED;
    if (length!=10) return UFS_LENGTH;
    if (cdb[0]!=0x28) return UFS_COMMAND;
    /* Strict READ(10) profile: no FUA/DPO/protection/group/control variants. */
    if (cdb[1] || cdb[6] || cdb[9]) return UFS_COMMAND;
    lba=be32(cdb+2); count=((uint32_t)cdb[7]<<8)|cdb[8];
    if (!count) return UFS_EXTENT;
    if (lba<h->policy.first_block || lba>=h->policy.lun_blocks ||
        count>h->policy.lun_blocks-lba ||
        lba-h->policy.first_block>=h->policy.extent_blocks ||
        count>h->policy.extent_blocks-(lba-h->policy.first_block) ||
        count-1>UINT32_MAX-lba) return UFS_EXTENT;
    bytes=count*h->policy.block_bytes;
    if (bytes>UFS_MAX_TRANSFER || bytes!=expected_bytes) return UFS_EXTENT;
    /* Do not wrap the 8-bit on-wire task tag within this retired epoch. */
    if (h->token.generation>=255) return UFS_EXHAUSTED;
    tag=h->token.generation+1;
    packet.bytes=(uint32_t)bytes;
    entries=((uint32_t)bytes+UFS_PRDT_CHUNK-1)/UFS_PRDT_CHUNK;
    packet.prdt_entries=entries;
    put32(packet.utrd,UINT32_C(0x15000000)); /* native storage, D2H, interrupt */
    put32(packet.utrd+8,15); /* invalid OCS until actual controller completion */
    put64(packet.utrd+16,h->policy.ucd_dma);
    put16(packet.utrd+24,128); put16(packet.utrd+26,128);
    put16(packet.utrd+28,entries); put16(packet.utrd+30,256);
    packet.ucd[0]=1; packet.ucd[1]=0x40;
    packet.ucd[2]=(uint8_t)h->policy.lun; packet.ucd[3]=(uint8_t)tag;
    putbe32(packet.ucd+12,(uint32_t)bytes);
    for (i=0;i<10;i++) packet.ucd[16+i]=cdb[i];
    for (i=0;i<entries;i++) {
        uint32_t chunk=(uint32_t)bytes-done;
        uint8_t *prd=packet.ucd+1024+i*16;
        if (chunk>UFS_PRDT_CHUNK) chunk=UFS_PRDT_CHUNK;
        put64(prd,h->policy.data_dma+done); put32(prd+12,chunk-1); done+=chunk;
    }
    h->packet=packet; h->token.generation=tag; h->token.tag=tag;
    h->phase=UFS_PREPARED;
    return UFS_OK;
}
uint32_t ufs_host_reserve_device(struct ufs_host *h, const struct ufs_token *t,
    uint64_t now, uint64_t timeout)
{
    if (!h || !h->policy.epoch) return UFS_ARGUMENT;
    if (!token_valid(h,t)) return UFS_STALE;
    if (h->phase!=UFS_PREPARED) return UFS_OWNERSHIP;
    if (!now || now<h->time_ns || !timeout || timeout>UFS_TIMEOUT_MAX_NS || timeout>UINT64_MAX-now)
        return UFS_CLOCK;
    h->time_ns=now; h->deadline_ns=now+timeout; h->phase=UFS_DEVICE_OWNED;
    return UFS_OK;
}
uint32_t ufs_host_poll_timeout(struct ufs_host *h, uint64_t now)
{
    if (!h || !h->policy.epoch) return UFS_ARGUMENT;
    if (h->phase!=UFS_DEVICE_OWNED) return UFS_OWNERSHIP;
    if (!now || now<h->time_ns) return UFS_CLOCK;
    h->time_ns=now;
    if (now>=h->deadline_ns) { h->phase=UFS_QUARANTINED; return UFS_TIMEOUT; }
    return UFS_OK;
}
uint32_t ufs_host_complete(struct ufs_host *h, const struct ufs_token *t,
    const uint8_t *cqe, size_t cqe_bytes, const uint8_t *rsp, size_t rsp_bytes, uint64_t now)
{
    uint64_t address;
    uint32_t i,r;
    if (!h || !cqe || !rsp || !h->policy.epoch) return UFS_ARGUMENT;
    if (!token_valid(h,t)) return UFS_STALE;
    if (h->phase!=UFS_DEVICE_OWNED) return UFS_OWNERSHIP;
    if (cqe_bytes!=UFS_CQE_BYTES || rsp_bytes<UFS_RESPONSE_MIN || rsp_bytes>512) return UFS_LENGTH;
    r=ufs_host_poll_timeout(h,now); if (r) return r;
    address=le64(cqe);
    if ((address&~UINT64_C(127))!=h->policy.ucd_dma || (address&31)!=h->policy.sqid)
        return UFS_STALE;
    if (address&96) return UFS_FORMAT; /* reserved bits6:5, not SQ ID */
    if (rsp[2]!=h->policy.lun || rsp[3]!=h->token.tag) return UFS_STALE;
    if (le16(cqe+8)!=128 || le16(cqe+10)!=128 ||
        le16(cqe+12)!=h->packet.prdt_entries || le16(cqe+14)!=256) return UFS_FORMAT;
    for (i=20;i<32;i++) if (cqe[i]) return UFS_FORMAT;
    /* Any matching error retains/quarantines the DMA lease. No automatic
       retries, hardware abort, clear/reset, cache maintenance or data copy. */
    if (le32(cqe+16) || rsp[0]!=0x21 || rsp[1] || rsp[4] || rsp[5] ||
        rsp[6] || rsp[7] || rsp[8] || rsp[9] || rsp[10] || rsp[11] ||
        be32(rsp+12) || rsp[32] || rsp[33]) {
        h->phase=UFS_QUARANTINED; return UFS_STATUS;
    }
    h->phase=UFS_COMPLETE;
    return UFS_OK;
}
uint32_t ufs_host_reclaim(struct ufs_host *h, const struct ufs_token *t)
{
    if (!h || !h->policy.epoch) return UFS_ARGUMENT;
    if (!token_valid(h,t)) return UFS_STALE;
    if (h->phase!=UFS_COMPLETE) return UFS_OWNERSHIP;
    h->phase=UFS_IDLE; return UFS_OK;
}
uint32_t ufs_host_cancel_prepared(struct ufs_host *h, const struct ufs_token *t)
{
    if (!h || !h->policy.epoch) return UFS_ARGUMENT;
    if (!token_valid(h,t)) return UFS_STALE;
    if (h->phase!=UFS_PREPARED) return UFS_OWNERSHIP;
    h->phase=UFS_IDLE; return UFS_OK;
}
