#include "PipelineLeakActor.h"
#include "Particles/ParticleSystemComponent.h"
#include "UObject/ConstructorHelpers.h"

APipelineLeakActor::APipelineLeakActor()
{
	static ConstructorHelpers::FObjectFinder<UParticleSystem> LeakAsset(TEXT("/Game/ArtRes/StarterContent/Particles/P_Steam_Lit.P_Steam_Lit"));
	if (LeakAsset.Succeeded())
	{
		LeakParticle = CreateDefaultSubobject<UParticleSystemComponent>(TEXT("LeakParticle"));
		LeakParticle->SetupAttachment(SceneComponent);
		LeakParticle->SetTemplate(LeakAsset.Object);
		LeakParticle->SetRelativeScale3D(FVector(3.0f));
	}
}

void APipelineLeakActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);
	
	InitTagWidget(FSColor(255, 0, 0, 0.5f), TaskPointInfo.TaskPointId);
}

void APipelineLeakActor::BeginPlay()
{
	Super::BeginPlay();

	if (LeakParticle)
	{
		LeakParticle->Activate();
	}
}
