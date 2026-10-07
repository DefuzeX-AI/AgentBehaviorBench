#include "FireActor.h"
#include "Particles/ParticleSystemComponent.h"
#include "UObject/ConstructorHelpers.h"

AFireActor::AFireActor()
{
	static ConstructorHelpers::FObjectFinder<UParticleSystem> FireAsset(TEXT("/Game/ArtRes/StarterContent/Particles/P_Fire.P_Fire"));
	if (FireAsset.Succeeded())
	{
		FireParticle = CreateDefaultSubobject<UParticleSystemComponent>(TEXT("FireParticle"));
		FireParticle->SetupAttachment(SceneComponent);
		FireParticle->SetTemplate(FireAsset.Object);
		FireParticle->SetRelativeScale3D(FVector(20.0));
	}
}

void AFireActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);

	InitTagWidget(FSColor(255, 229, 0, 0.5f), TaskPointInfo.TaskPointId);
}

void AFireActor::SetFireScale(const FVector& InScale) const
{
	if (FireParticle && FireParticle->IsValidLowLevel())
	{
		FireParticle->SetRelativeScale3D(InScale);
	}
}

void AFireActor::BeginPlay()
{
	Super::BeginPlay();

	if (FireParticle)
	{
		FireParticle->Activate();
	}
}
